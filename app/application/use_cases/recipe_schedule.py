"""N20–N22 retained editor with current authority, ordered fences and atomic writes."""
import base64
import hashlib
import hmac
import json
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.application.contracts import recipe_schedule as dto
from app.application.contracts.auth import AuthError, Pagination
from app.application.contracts.recipe import CreateRecipeVersionInput
from app.application.use_cases.recipe import RecipeUseCases
from app.application.recipe_schedule_plan import READS, normalized_request, propose, periods
from app.application.import_identity import content_digest
from app.domain.recipe_calendar import history_unchanged, overlaps
from app.infrastructure.database.auth_session import auth_session
from app.infrastructure.auth_crypto import CursorSigner
from app.models import Store, Recipe
from app.models.recipe_schedule import RecipeScheduleChange, RecipeScheduleRequestReceipt
from app.repositories.recipe_schedule import capture_calendar, fence_calendar, change_row


class RecipeSchedule:
    def __init__(self, auth):
        self.auth, self.engine = auth, auth.engine
        self.signer = CursorSigner()

    @staticmethod
    def _bounded(value, *, retained=False):
        limit = 4 * 1024 * 1024 if retained else 1024 * 1024
        if len(value.model_dump_json().encode("utf-8")) > limit:
            raise AuthError("CATALOG_REPRESENTATION_UNAVAILABLE",503)
        return value

    def _authorize(self, token, store):
        with auth_session(self.engine) as s:
            actor, authorization, _ = self.auth.authorize_in_session(s,token,store,READS)
            s.commit()
            return actor, authorization

    def _day(self, s, store):
        now = self.auth.clock()
        today = now.astimezone(ZoneInfo(s.get(Store,store).timezone)).date()
        if today == date.max:
            raise AuthError("INVALID_DATE_RANGE",422)
        return now, today

    def timeline(self, token, store, product, *, status="in_effect,scheduled", limit=50,
                 cursor=None, sort="effective_from,version", from_date=None, to_date=None):
        states = status.split(",")
        if (not states or len(set(states)) != len(states) or
            not set(states) <= {"past","in_effect","scheduled","unassigned"} or
            sort != "effective_from,version" or not 1 <= limit <= 100 or
            (from_date is not None and to_date is not None and from_date > to_date)):
            raise AuthError("INVALID_FILTER",422)
        actor, authorization = self._authorize(token,store)
        with self.engine.connect().execution_options(isolation_level="REPEATABLE READ",postgresql_readonly=True) as connection:
            with auth_session(connection) as s:
                _, today = self._day(s,store)
                snap = capture_calendar(s,store,product,today)
                items = tuple(i for i in snap.items if i.state in states and (
                    from_date is None and to_date is None or i.assignment is not None and
                    (from_date is None or (i.assignment.effective_to or date.max) >= from_date) and
                    (to_date is None or i.assignment.effective_from <= to_date)))
                binding = dict(actor=str(actor.user_id),store=str(store),product=str(product),
                    status=sorted(states),limit=limit,sort=sort,
                    from_date=str(from_date),to_date=str(to_date))
                snapshot = content_digest([snap.schedule_version,snap.catalog_version,str(today),authorization.authorization_version])
                offset = 0
                if cursor:
                    try:
                        payload,signature = cursor.split(".")
                        if not hmac.compare_digest(signature,self.signer.sign(token,"recipe_schedule",payload)):
                            raise ValueError()
                        values = json.loads(base64.urlsafe_b64decode(payload))
                        if values["binding"] != binding:
                            raise ValueError()
                        if values["snapshot"] != snapshot:
                            raise AuthError("LIST_VERSION_CHANGED",409)
                        offset = values["offset"]
                        if type(offset) is not int or not 0 < offset < len(items):
                            raise ValueError()
                    except (ValueError,TypeError,KeyError):
                        raise AuthError("INVALID_CURSOR",422) from None
                next_cursor = None
                if offset + limit < len(items):
                    payload = base64.urlsafe_b64encode(json.dumps(dict(binding=binding,snapshot=snapshot,offset=offset+limit),sort_keys=True).encode()).decode()
                    next_cursor = payload+"."+self.signer.sign(token,"recipe_schedule",payload)
                result = dto.Timeline(store_id=store,product_id=product,as_of_date=today,
                    schedule_version=snap.schedule_version,catalog_version=snap.catalog_version,
                    items=items[offset:offset+limit],minimum_change_date=today+timedelta(days=1))
        _, current = self._authorize(token,store)
        if current.authorization_version != authorization.authorization_version:
            raise AuthError("LIST_VERSION_CHANGED",409)
        return self._bounded(result), Pagination(limit=limit,next_cursor=next_cursor,total_count=len(items))

    @staticmethod
    def _preview(row):
        try:
            preview = dto.Preview.model_validate(row.preview_json)
            if (preview.change_id != row.id or preview.store_id != row.store_id or preview.product_id != row.product_id or
                content_digest(preview.model_dump(mode="json",exclude={"preview_digest"})) != preview.preview_digest):
                raise ValueError()
            return preview
        except (ValueError,ValidationError):
            raise AuthError("CATALOG_INTEGRITY_UNAVAILABLE",503) from None

    @staticmethod
    def _change(s, store, product, ident):
        return change_row(s,store,product,ident)

    def read_change(self, token, store, product, ident):
        with auth_session(self.engine) as s:
            self.auth.authorize_in_session(s,token,store,READS)
            row = self._change(s,store,product,ident)
            preview = self._preview(row)
            receipt = dto.Receipt.model_validate(row.receipt_json) if row.receipt_json is not None else None
            audit = dto.Audit.model_validate(row.audit_json) if row.audit_json is not None else None
            result = dto.ChangeRead(change_id=row.id,status="committed" if receipt else preview.status,
                preview=preview,receipt=receipt,audit=audit)
            s.commit()
            return self._bounded(result,retained=True)

    @staticmethod
    def _headers(key, match):
        if key is None or match is None:
            raise AuthError("PRECONDITION_REQUIRED",428)
        try:
            if str(UUID(key)) != key:
                raise ValueError()
            if not (match.startswith('"') and match.endswith('"')) or not match[1:-1] or any(c in match[1:-1] for c in ('"',",","*")):
                raise ValueError()
        except (ValueError,TypeError,AttributeError):
            raise AuthError("VALIDATION_ERROR",422) from None
        return hashlib.sha256(key.encode()).hexdigest(), match[1:-1]

    def _rights(self, s, token, store, product, body, csrf):
        actor, _, permissions = self.auth.authorize_in_session(s,token,store,(*READS,"recipe.manage_effectivity"),csrf=csrf)
        if isinstance(body,dto.PreviewRequest):
            new_content = bool(body.new_recipes)
        else:
            new_content = bool(self._preview(self._change(s,store,product,body.change_id)).new_contents)
        if new_content and "recipe.create_version" not in permissions:
            raise AuthError("PERMISSION_DENIED")
        return actor

    @staticmethod
    def _old(s, identity, request_digest, body):
        row = s.get(RecipeScheduleRequestReceipt,identity)
        if row is None:
            return None
        if row.request_digest != request_digest:
            raise AuthError("IDEMPOTENCY_KEY_REUSED",409)
        cls = dto.Preview if isinstance(body,dto.PreviewRequest) else dto.Receipt
        return cls.model_validate(row.record_json)

    def change(self, token, store, product, body, key, match, csrf, request_id):
        key_digest, version = self._headers(key,match)
        normalized = normalized_request(body)
        request_digest = content_digest([normalized,version])
        try:
            with auth_session(self.engine) as s:
                actor = self._rights(s,token,store,product,body,csrf or "")
                identity = (actor.user_id,store,product,body.phase,key_digest)
                old = self._old(s,identity,request_digest,body)
                if old is not None:
                    s.commit()
                    return old
                fence_calendar(s)
                now,today = self._day(s,store)
                if isinstance(body,dto.PreviewRequest):
                    snap = capture_calendar(s,store,product,today)
                    if version != snap.schedule_version:
                        raise AuthError("RECIPE_SCHEDULE_REVISION_CONFLICT",412)
                    result = propose(dto.PreviewRequest.model_validate(normalized),store=store,product=product,
                        today=today,now=now,before=snap.items,selling_unit=snap.selling_unit,ingredients=snap.ingredients,
                        schedule_version=snap.schedule_version,catalog_version=snap.catalog_version)
                    if len(result.model_dump_json().encode("utf-8")) > 1024 * 1024:
                        raise AuthError("RESOURCE_LIMIT_EXCEEDED",413)
                    s.add(RecipeScheduleChange(id=result.change_id,store_id=store,product_id=product,actor_id=actor.user_id,
                        created_at=now,preview_json=result.model_dump(mode="json"),proposal_json=normalized))
                else:
                    result = self._commit(s,actor,store,product,body,version,now,today,request_id)
                s.add(RecipeScheduleRequestReceipt(actor_id=actor.user_id,store_id=store,product_id=product,phase=body.phase,
                    key_digest=key_digest,request_digest=request_digest,record_json=result.model_dump(mode="json")))
                s.commit()
                return result
        except AuthError:
            raise
        except Exception as error:
            # Unknown commit ACK is resolved by current authorization + retained proof,
            # never by a speculative second application of calendar operations.
            try:
                with auth_session(self.engine) as fresh:
                    actor = self._rights(fresh,token,store,product,body,csrf or "")
                    old = self._old(fresh,(actor.user_id,store,product,body.phase,key_digest),request_digest,body)
                    if old is not None:
                        change = self._change(fresh,store,product,old.change_id)
                        self._preview(change)
                        if isinstance(old,dto.Receipt) and change.receipt_json != old.model_dump(mode="json"):
                            raise ValueError("receipt proof mismatch")
                        fresh.commit()
                        return old
            except AuthError:
                raise
            except Exception:
                pass
            if isinstance(error,IntegrityError) and getattr(error.orig,"sqlstate",None) in {"23505","23P01","23503"}:
                raise AuthError("PREVIEW_STALE",409) from None
            raise AuthError("SERVICE_UNAVAILABLE",503) from None

    def _commit(self, s, actor, store, product, body, version, now, today, request_id):
        row = self._change(s,store,product,body.change_id)
        preview = self._preview(row)
        if row.receipt_json is not None:
            raise AuthError("RECIPE_CHANGE_NOT_READY",409)
        if body.preview_digest != preview.preview_digest:
            raise AuthError("PREVIEW_STALE",409)
        if today != preview.as_of_date:
            raise AuthError("RECIPE_DATE_POLICY_CHANGED",409)
        try:
            snap = capture_calendar(s,store,product,today)
        except AuthError as error:
            if error.code == "CATALOG_INTEGRITY_UNAVAILABLE":
                raise AuthError("PREVIEW_STALE",409) from None
            raise
        old_contents = {i.content.recipe_id:i.content for i in preview.before}
        if any(i.content.recipe_id in old_contents and i.content != old_contents[i.content.recipe_id] for i in snap.items):
            raise AuthError("PREVIEW_STALE",409)
        if version != snap.schedule_version or version != preview.schedule_version:
            raise AuthError("RECIPE_SCHEDULE_REVISION_CONFLICT",412)
        if snap.catalog_version != preview.catalog_version or snap.items != preview.before:
            raise AuthError("PREVIEW_STALE",409)
        if not preview.can_commit or preview.blockers:
            raise AuthError("PREVIEW_BLOCKED",409)
        if (len(set(body.acknowledged_warning_codes)) != len(body.acknowledged_warning_codes) or
            set(body.acknowledged_warning_codes) != set(preview.required_warning_acknowledgements)):
            raise AuthError("INVALID_WARNING_ACKNOWLEDGEMENT",422)
        if not history_unchanged(periods(snap.items),periods(preview.after),today) or overlaps(periods(preview.after)):
            raise AuthError("PREVIEW_BLOCKED",409)
        previous = {i.content.recipe_id:i for i in preview.before}
        affected = tuple(i.content.recipe_id for i in preview.after if previous.get(i.content.recipe_id) != i)
        # Temporarily unassign changed existing rows only inside this transaction.
        # This supports future swaps without transient exclusion failures; external
        # readers see either complete before or complete after via MVCC.
        existing = {}
        for ident in affected:
            if ident in previous:
                existing[ident] = s.get(Recipe,ident)
                existing[ident].assigned = False
        s.flush()
        new_ids = {c.recipe_id for c in preview.new_contents}
        for item in preview.after:
            content, assignment = item.content,item.assignment
            if content.recipe_id not in affected:
                continue
            if content.recipe_id in new_ids:
                RecipeUseCases(s).create_in_transaction(CreateRecipeVersionInput(store_id=store,product_id=product,
                    version=content.version,effective_from=assignment.effective_from,effective_to=assignment.effective_to,
                    yield_quantity=Decimal(content.yield_quantity),process_loss_rate=Decimal(content.process_loss_rate),
                    lines=tuple(dict(ingredient_id=l.ingredient_id,quantity=Decimal(l.quantity),unit=l.unit) for l in content.ingredients)),
                    reserved_id=content.recipe_id,reserved_line_ids={l.ingredient_id:l.recipe_line_id for l in content.ingredients})
            elif assignment is not None:
                record = existing[content.recipe_id]
                record.effective_from,record.effective_to,record.assigned = assignment.effective_from,assignment.effective_to,True
            s.flush()
        after = capture_calendar(s,store,product,today)
        if after.items != preview.after:
            raise AuthError("PREVIEW_STALE",409)
        receipt = dto.Receipt(change_id=row.id,preview_digest=preview.preview_digest,store_id=store,product_id=product,
            committed_at=now,schedule_version_before=preview.schedule_version,schedule_version_after=after.schedule_version,
            created_recipe_ids=tuple(c.recipe_id for c in preview.new_contents),affected_recipe_ids=affected,
            audit_reference=uuid4(),changed=bool(affected),updated_resources=dto.UpdatedResources(menu=bool(affected),recipes=bool(affected)),
            warnings=preview.warnings)
        audit = dto.Audit(change_id=row.id,actor_user_id=actor.user_id,store_id=store,product_id=product,
            reason=row.proposal_json["reason"],occurred_at=now,preview_digest=preview.preview_digest,
            calendar_before_version=preview.schedule_version,calendar_after_version=after.schedule_version,
            before=preview.before,after=preview.after,new_content_ids=receipt.created_recipe_ids,
            operations=dto.PreviewRequest.model_validate(row.proposal_json).operations,
            acknowledged_warnings=body.acknowledged_warning_codes,request_id=request_id)
        row.receipt_json,row.audit_json = receipt.model_dump(mode="json"),audit.model_dump(mode="json")
        s.flush()
        return receipt
