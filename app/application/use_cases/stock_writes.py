"""N6/N8 scoped current-auth/CAS writes and immutable replay receipts."""
from datetime import timezone
from decimal import Decimal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo
import hashlib, json
from sqlalchemy import select, text
from pydantic import ValidationError
from app.application.contracts.auth import AuthError
from app.application.contracts import stock_writes as dto
from app.application.contracts.public_reads import MovementRead, MovementReference
from app.application.contracts.inventory import ReceiveInventoryInput
from app.application.errors import ApplicationError, ErrorCategory
from app.application.use_cases.inventory import InventoryUseCases
from app.application.use_cases.public_reads import opaque, issue
from app.domain.inventory.read_rules import decimal_text
from app.infrastructure.database.auth_session import auth_session
from app.models import Ingredient, InventoryLot, InventoryMovement
from app.models.operational_import import InventoryReceiptRecord, InventoryAudit, InventoryThreshold, StockRequestReceipt
from app.repositories.public_reads import PublicReadRepository
from app.application.use_cases.auth import AuthUseCases
from app.application.use_cases.public_reads import PublicReads
from app.application.stock_observation import validate_opening_observation

def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()

def normalized(body):
    values = body.model_dump(mode="json")
    for key in ("quantity", "unit_cost", "minimum_usable_quantity"):
        if values.get(key) is not None:
            value = decimal_text(Decimal(values[key]))
            values[key] = value.rstrip("0").rstrip(".") if "." in value else value
    if "observed_at" in values:
        values["observed_at"] = body.observed_at.astimezone(timezone.utc).isoformat()
    return values

class StockWrites:
    def __init__(self, auth: AuthUseCases, reads: PublicReads):
        self.auth, self.reads, self.engine = auth, reads, auth.engine

    @staticmethod
    def _visible(result, permissions):
        if isinstance(result, dto.StockReceiptResult):
            cost = result.lot.cost
            visible = "procurement.cost.read" in permissions
            cost = cost.model_copy(update={"availability":("known" if cost.unit_cost is not None else "unknown") if visible else "forbidden",
                                          "unit_cost":cost.unit_cost if visible else None})
            result = result.model_copy(update={"lot":result.lot.model_copy(update={"cost":cost})})
        return result

    def _run(self, token, store, body, key, csrf, operation, required, result_type, action, *, owner=False, match=None):
        if not key:
            raise AuthError("PRECONDITION_REQUIRED", 428)
        try:
            if str(UUID(key)) != key:raise ValueError()
        except (ValueError,TypeError,AttributeError):
            raise AuthError("VALIDATION_ERROR",422) from None
        request_digest = fingerprint(dict(body=normalized(body), match=match))
        key_digest = hashlib.sha256(key.encode()).hexdigest()
        try:
            with auth_session(self.engine) as s:
                actor, authorization, permissions = self.auth.authorize_in_session(s, token, store, required, owner_only=owner, csrf=csrf)
                identity = (actor.user_id, store, operation, key_digest)
                old = s.get(StockRequestReceipt, identity)
                if old:
                    if old.request_digest != request_digest:
                        raise AuthError("IDEMPOTENCY_KEY_REUSED", 409)
                    result = result_type.model_validate(old.record_json)
                    s.commit()
                    return self._visible(result, permissions), True
                # Consistent with Import's canonical fences, including internal writers.
                for table in sorted(("ingredients", "inventory_lots", "inventory_movements", "inventory_thresholds")):
                    s.execute(text('LOCK TABLE "' + table + '" IN SHARE ROW EXCLUSIVE MODE'))
                repo = PublicReadRepository(s)
                basis = repo.basis(store)
                now = self.auth.clock()
                today = now.astimezone(ZoneInfo(basis["timezone"])).date()
                result, replay = action(s, actor, authorization, permissions, repo, basis, now, today)
                s.add(StockRequestReceipt(actor_id=actor.user_id, store_id=store, operation=operation,
                    key_digest=key_digest, request_digest=request_digest, record_json=result.model_dump(mode="json")))
                s.commit()
                return self._visible(result, permissions), replay
        except AuthError:
            raise
        except (ApplicationError, ValidationError) as error:
            if isinstance(error, ApplicationError) and error.category == ErrorCategory.NOT_FOUND:
                raise AuthError("RESOURCE_NOT_FOUND", 404) from None
            raise AuthError("VALIDATION_ERROR", 422) from None
        except Exception:
            # Unknown commit acknowledgement: return success only on durable receipt proof,
            # after current authorization. No speculative second canonical execution.
            try:
                with auth_session(self.engine) as fresh:
                    actor, _, permissions = self.auth.authorize_in_session(fresh, token, store, required, owner_only=owner, csrf=csrf)
                    old = fresh.get(StockRequestReceipt, (actor.user_id, store, operation, key_digest))
                    if old and old.request_digest == request_digest:
                        result = result_type.model_validate(old.record_json)
                        fresh.commit()
                        return self._visible(result, permissions), True
            except AuthError:
                raise
            except Exception:
                pass
            raise AuthError("SERVICE_UNAVAILABLE", 503) from None

    def receive(self, token: str | None, store: UUID, body: dto.StockReceiptRequest,
                key: str | None, csrf: str | None) -> tuple[dto.StockReceiptResult, bool]:
        body = dto.StockReceiptRequest.model_validate(body)
        required = ("inventory.receive", "inventory.read", "ingredient.read")
        if body.unit_cost is not None:
            required += ("procurement.cost.read",)
        semantic = normalized(body)
        semantic.pop("expected_inventory_version")
        payload_digest = fingerprint(semantic)
        def action(s, actor, authorization, permissions, repo, basis, now, today):
            old = s.scalar(select(InventoryReceiptRecord).where(InventoryReceiptRecord.store_id == store,
                InventoryReceiptRecord.source_system_key == body.receipt_identity.source_system_key,
                InventoryReceiptRecord.source_record_key == body.receipt_identity.source_record_id))
            if old:
                if old.payload_digest != payload_digest:
                    raise AuthError("RECEIPT_IDENTITY_CONFLICT", 409)
                return dto.StockReceiptResult.model_validate(old.record_json), True
            ingredient = repo.ingredient(store, body.ingredient_id)
            if ingredient is None:
                raise AuthError("RESOURCE_NOT_FOUND", 404)
            version, _ = self.reads.snapshot_identity(token, store, actor, authorization, permissions, basis, today)
            if version != body.expected_inventory_version:
                raise AuthError("INVENTORY_VERSION_CONFLICT", 409)
            if body.unit != ingredient["base_unit"]:
                raise AuthError("INVALID_UNIT",422)
            if ingredient["expiry_tracking"] and body.expiry_date is None:
                raise AuthError("REQUIRED_EXPIRY_MISSING",422)
            if body.currency != basis["currency"]:
                raise AuthError("VALIDATION_ERROR", 422)
            if body.observed_at > now:
                raise AuthError("STALE_STOCK_OBSERVATION",409)
            if body.origin == "OPENING_STOCK":
                validate_opening_observation(s, store, body.ingredient_id, body.observed_at, body.lot_code)
            if body.received_date is not None and body.received_date > today:
                raise AuthError("VALIDATION_ERROR", 422)
            rid, aid = uuid4(), uuid4()
            mutation = InventoryUseCases(s).receive_in_transaction(ReceiveInventoryInput(
                store_id=store, ingredient_id=body.ingredient_id, supplier_id=body.supplier_id,
                lot_code=body.lot_code, quantity=Decimal(body.quantity), unit=body.unit,
                received_date=body.received_date, expiry_date=body.expiry_date,
                unit_cost=Decimal(body.unit_cost) if body.unit_cost is not None else None,
                occurred_at=body.observed_at, reference_type=body.origin, reference_id=str(rid), note=body.reason),
                opening=body.origin == "OPENING_STOCK")
            movement = s.get(InventoryMovement, mutation.movement.id)
            s.add(InventoryAudit(id=aid, store_id=store, actor_id=actor.user_id, movement_id=movement.id,
                occurred_at=now, record_json=dict(origin=body.origin, receipt_id=str(rid), request=semantic)))
            s.flush()
            version, _ = self.reads.snapshot_identity(token, store, actor, authorization, permissions, repo.basis(store), today)
            lots, _, first = repo.lots(store, ingredient, today, None, 100, True)
            row = next((r for r in lots if r["id"] == mutation.lot.id), None)
            if row is None:
                lot = s.get(InventoryLot, mutation.lot.id)
                row = {c.name: getattr(lot, c.name) for c in InventoryLot.__table__.columns}
            lot = self.reads._lot(row, ingredient, today, first, basis["currency"], "procurement.cost.read" in permissions, version)
            lot = lot.model_copy(update={"origin": body.origin})
            warnings = []
            for condition, code, field in ((body.received_date is None, "MISSING_RECEIVED_DATE", "received_date"),
                (body.expiry_date is not None and body.expiry_date < today, "LOT_EXPIRED", "expiry_date"),
                (body.origin == "ACTUAL_RECEIPT" and (body.observed_at.astimezone(ZoneInfo(basis["timezone"])).date() < today
                 or (body.received_date is not None and body.received_date < today)), "LATE_RECEIPT_RECORDED", "observed_at")):
                if condition:
                    warnings.append(issue(code, "inventory_lot", mutation.lot.id, field, code))
            result = dto.StockReceiptResult(receipt_id=rid, origin=body.origin, lot=lot,
                movement=MovementRead(movement_id=movement.id, lot_id=movement.lot_id, batch_code=body.lot_code,
                    kind=movement.movement_type.lower(), quantity_delta=decimal_text(movement.quantity_delta), unit=body.unit,
                    occurred_at=movement.occurred_at, recorded_at=movement.created_at, actor_user_id=actor.user_id,
                    reason=body.reason, reference=MovementReference(type=body.origin, id=str(rid)), origin=body.origin),
                inventory_version=version, audit_reference=aid, warnings=tuple(warnings))
            s.add(InventoryReceiptRecord(id=rid, store_id=store, source_system_key=body.receipt_identity.source_system_key,
                source_record_key=body.receipt_identity.source_record_id, ingredient_id=body.ingredient_id,
                lot_id=mutation.lot.id, origin=body.origin, payload_digest=payload_digest, record_json=result.model_dump(mode="json")))
            return result, False
        return self._run(token, store, body, key, csrf, "N6", required, dto.StockReceiptResult, action)

    def threshold(self, token: str | None, store: UUID, ingredient_id: UUID, body: dto.ThresholdRequest,
                  key: str | None, csrf: str | None, match: str | None) -> tuple[dto.ThresholdResult, bool]:
        body = dto.ThresholdRequest.model_validate(body)
        if not match:
            raise AuthError("PRECONDITION_REQUIRED", 428)
        if not (match.startswith('"') and match.endswith('"')) or any(c in match[1:-1] for c in ('"',",","*")) or not match[1:-1]:
            raise AuthError("VALIDATION_ERROR",422)
        version = match[1:-1]
        def action(s, actor, authorization, permissions, repo, basis, now, today):
            ingredient = repo.ingredient(store, ingredient_id)
            if ingredient is None:
                raise AuthError("RESOURCE_NOT_FOUND", 404)
            current = s.get(InventoryThreshold, (store, ingredient_id))
            current_version = current.version if current else "unconfigured-" + opaque(str(ingredient_id))
            if current_version != version:
                raise AuthError("THRESHOLD_REVISION_CONFLICT", 412)
            if body.unit != ingredient["base_unit"]:
                raise AuthError("INVALID_UNIT", 422)
            quantity = Decimal(body.minimum_usable_quantity) if body.minimum_usable_quantity is not None else None
            if current is not None and current.minimum_usable_quantity == quantity:
                return dto.ThresholdResult(ingredient_id=ingredient_id, minimum_usable_quantity=None if quantity is None else decimal_text(quantity),
                    unit=current.unit, version=current.version, updated_at=current.updated_at, updated_by=current.updated_by), False
            before = current.minimum_usable_quantity if current else None
            if current is None:
                current = InventoryThreshold(store_id=store, ingredient_id=ingredient_id, unit=body.unit)
                s.add(current)
            current.minimum_usable_quantity, current.version = quantity, "threshold-" + str(uuid4())
            current.updated_at, current.updated_by = now, actor.user_id
            s.add(InventoryAudit(id=uuid4(), store_id=store, actor_id=actor.user_id, movement_id=None, occurred_at=now,
                record_json=dict(operation="N8", ingredient_id=str(ingredient_id), before=str(before) if before is not None else None,
                    after=body.minimum_usable_quantity, reason=body.reason, version=current.version)))
            s.flush()
            return dto.ThresholdResult(ingredient_id=ingredient_id, minimum_usable_quantity=body.minimum_usable_quantity,
                unit=current.unit, version=current.version, updated_at=current.updated_at, updated_by=current.updated_by), False
        return self._run(token, store, body, key, csrf, "N8:" + str(ingredient_id), ("inventory.read", "ingredient.read"),
            dto.ThresholdResult, action, owner=True, match=version)
