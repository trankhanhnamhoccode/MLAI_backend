"""Detached public Menu and inventory projections over one coherent snapshot."""

import base64
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib, hmac, json
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from app.application.contracts.auth import AuthError, Pagination
from app.application.contracts import public_reads as dto
from app.domain.inventory.read_rules import (
    decimal_text,
    fold_name,
    lot_status,
    ReadFactError,
    MAX_RESPONSE_BYTES,
)
from app.infrastructure.auth_crypto import CursorSigner
from app.infrastructure.database.auth_session import auth_session
from app.infrastructure.database.public_read_session import public_read_snapshot


def opaque(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str).encode()
    ).hexdigest()


def issue(code, entity, identifier, field, impact, *, error=False):
    return dto.Notification(
        code=code,
        message=impact,
        details=dto.IssueDetails(
            entity=entity,
            entity_id=identifier,
            field=field,
            severity="DATA_ERROR" if error else "WARNING",
            impact=impact,
        ),
    )


class PublicReads:
    def __init__(self, auth):
        self.auth, self.engine, self.clock = auth, auth.engine, auth.clock
        # Private owned process key, never derived solely from client-held values.
        self._cursor_signer = CursorSigner()

    def _mac(self, token: str, payload: str) -> str:
        return self._cursor_signer.sign(token, "public_reads", payload)

    def _authorize(self, token, store, required):
        with auth_session(self.engine) as s:
            actor, summary, permissions = self.auth.authorize_in_session(
                s, token, store, required
            )
            s.commit()
        return actor, summary, permissions

    def snapshot_identity(self, token, store, actor, authorization, permissions, basis, today, catalog=False):
        """Same session-bound version for GET and transaction-owned stock CAS."""
        recipes = {"recipe.read", "ingredient.read"} <= set(permissions)
        revision = ([basis["menu_revision"], basis["recipe_revision"]] if catalog and recipes
                    else [basis["menu_revision"]] if catalog
                    else [basis["recipe_revision"], basis["inventory_revision"]])
        identity = [str(actor.user_id), str(store), authorization.authorization_version,
                    str(today), basis["timezone"], basis["currency"], revision, catalog, recipes]
        return ("catalog-" if catalog else "stock-") + self._mac(token, json.dumps(identity, default=str)), identity

    def _read(self, token, store, required, catalog, request_id, build):
        try:
            actor, authorization, permissions = self._authorize(token, store, required)
            with public_read_snapshot(self.engine) as repo:
                basis = repo.basis(store)
                if not basis or not basis["active"]:
                    raise AuthError("RESOURCE_NOT_FOUND", 404)
                if any(
                    basis[key] is None
                    for key in (
                        "menu_revision",
                        "recipe_revision",
                        "inventory_revision",
                    )
                ):
                    raise ReadFactError()
                observed = self.clock()
                if observed.tzinfo is None or observed.utcoffset() is None:
                    raise ReadFactError()
                observed = observed.astimezone(timezone.utc)
                today = observed.astimezone(ZoneInfo(basis["timezone"])).date()
                recipes = {"recipe.read", "ingredient.read"} <= set(permissions)
                # Opaque snapshot token is MAC-bound to authenticated session/scope.
                snapshot, identity = self.snapshot_identity(token, store, actor, authorization, permissions, basis, today, catalog)
                updated = repo.updated(store, catalog=catalog, recipes=recipes)
                data, extra = build(repo, basis, today, snapshot, identity, permissions)
                meta = (
                    dto.CatalogMeta(
                        request_id=request_id,
                        observed_at=observed,
                        as_of_date=today,
                        timezone=basis["timezone"],
                        updated_at=updated,
                        data_version=snapshot,
                        **extra
                    )
                    if catalog
                    else dto.InventoryMeta(
                        request_id=request_id,
                        as_of_date=today,
                        updated_at=updated,
                        snapshot_id=snapshot,
                        data_version=snapshot,
                        **extra
                    )
                )
            # Auth state can change while the separate read-only snapshot runs.
            _, current, _ = self._authorize(token, store, required)
            if current.authorization_version != authorization.authorization_version:
                raise AuthError(
                    "LIST_VERSION_CHANGED" if catalog else "SNAPSHOT_NOT_AVAILABLE", 409
                )
            cls = (
                dto.CatalogEnvelope[type(data)]
                if catalog
                else dto.InventoryEnvelope[type(data)]
            )
            result = cls(data=data, meta=meta, error=None)
            if len(result.model_dump_json().encode()) > MAX_RESPONSE_BYTES:
                raise ReadFactError(True)
            return result
        except ReadFactError as error:
            code = (
                "CATALOG_REPRESENTATION_UNAVAILABLE"
                if error.representation
                else "CATALOG_INTEGRITY_UNAVAILABLE"
            )
            raise AuthError(code if catalog else "SERVICE_UNAVAILABLE", 503) from None
        except (ValidationError, ZoneInfoNotFoundError, OverflowError):
            raise AuthError(
                "CATALOG_INTEGRITY_UNAVAILABLE" if catalog else "SERVICE_UNAVAILABLE",
                503,
            ) from None
        except SQLAlchemyError:
            raise AuthError(
                "CATALOG_READ_UNAVAILABLE" if catalog else "SERVICE_UNAVAILABLE", 503
            ) from None

    def _cursor(self, token, cursor, binding, snapshot, *, catalog, kind):
        if cursor is None:
            return None
        try:
            payload, signature = cursor.split(".")
            if not hmac.compare_digest(
                self._mac(token, payload),
                signature,
            ):
                raise ValueError()
            values = json.loads(base64.urlsafe_b64decode(payload))
            if values["binding"] != binding:
                raise ValueError()
            if values["snapshot"] != snapshot:
                raise AuthError(
                    "LIST_VERSION_CHANGED" if catalog else "SNAPSHOT_NOT_AVAILABLE", 409
                )
            key = values["key"]
            uid = UUID(key[-1])
            if kind == "lots":
                return (date.fromisoformat(key[0]) if key[0] else None, key[1], uid)
            if kind == "movements":
                return datetime.fromisoformat(key[0]), uid
            value = key[0]
            if kind == "money" and value is not None:
                value = Decimal(value)
            if kind == "date" and value is not None:
                value = date.fromisoformat(value)
            return value, uid
        except (ValueError, KeyError, TypeError, IndexError):
            raise AuthError("INVALID_CURSOR", 422) from None

    def _page(self, rows, total, limit, token, binding, snapshot, *, kind):
        cursor = None
        if len(rows) > limit:
            row = rows[limit - 1]
            key = (
                [row["expiry_date"], row["lot_code"], row["id"]]
                if kind == "lots"
                else (
                    [row["occurred_at"], row["id"]]
                    if kind == "movements"
                    else [row["sort_key"], row["id"]]
                )
            )
            payload = base64.urlsafe_b64encode(
                json.dumps(
                    dict(binding=binding, snapshot=snapshot, key=key), default=str
                ).encode()
            ).decode()
            cursor = payload + "." + self._mac(token, payload)
        return rows[:limit], Pagination(
            limit=limit, next_cursor=cursor, total_count=total
        )

    def _product(self, row, currency):
        if not row["name"].strip() or not row["selling_unit"].strip():
            raise ReadFactError()
        return dict(
            product_id=row["id"],
            sku=row["sku"],
            name=row["name"],
            selling_unit=row["selling_unit"],
            selling_price=(
                decimal_text(row["price"], money=True)
                if row["price"] is not None
                else None
            ),
            currency=currency,
            status="active" if row["active"] else "paused",
        )

    def _recipes(self, rows):
        results = {}
        for row in rows:
            if (
                row["product_id"] in results
                or row["invalid_lines"]
                or row["duplicate_lines"]
                or row["version"] <= 0
            ):
                raise ReadFactError()
            decimal_text(row["yield_quantity"], positive=True)
            decimal_text(row["process_loss_rate"])
            if row["process_loss_rate"] >= 1:
                raise ReadFactError()
            results[row["product_id"]] = row
        return results

    def menu(
        self,
        token,
        store,
        request_id,
        *,
        q=None,
        status=None,
        sort="name",
        limit=50,
        cursor=None
    ):
        def build(repo, basis, today, snapshot, identity, permissions):
            binding = [str(identity[0]), str(store), "menu", q, status, sort, limit]
            kind = "money" if "selling_price" in sort else "text"
            last = self._cursor(
                token, cursor, binding, snapshot, catalog=True, kind=kind
            )
            rows, total, summary = repo.products(
                store, fold_name(q) if q else None, status, sort, last, limit
            )
            rows, page = self._page(
                rows, total, limit, token, binding, snapshot, kind=kind
            )
            allowed = {"recipe.read", "ingredient.read"} <= set(permissions)
            recipes = (
                self._recipes(repo.recipes(store, [r["id"] for r in rows], today))
                if allowed and rows
                else {}
            )
            items = []
            warnings = []
            for row in rows:
                recipe = recipes.get(row["id"])
                availability = (
                    "forbidden"
                    if not allowed
                    else "available" if recipe else "missing_recipe"
                )
                if allowed and not recipe:
                    warnings.append(
                        issue(
                            "RECIPE_NOT_AVAILABLE",
                            "product",
                            row["id"],
                            "recipe",
                            "Không có công thức hiệu lực tại ngày đọc",
                        )
                    )
                if recipe and recipe["line_count"] == 0:
                    warnings.append(
                        issue(
                            "EMPTY_RECIPE",
                            "product",
                            row["id"],
                            "recipe",
                            "Công thức hiện hành không có nguyên liệu",
                        )
                    )
                items.append(
                    dto.ProductRow(
                        **self._product(row, basis["currency"]),
                        ingredient_count=recipe["line_count"] if recipe else None,
                        ingredient_count_availability=availability
                    )
                )
            return dto.Menu(
                summary=dto.MenuSummary(**summary), items=tuple(items)
            ), dict(pagination=page, warnings=tuple(warnings))

        return self._read(token, store, ("menu.read",), True, request_id, build)

    def product(self, token, store, identifier, request_id):
        def build(repo, basis, today, snapshot, identity, permissions):
            row = repo.product(store, identifier)
            if row is None:
                raise AuthError("RESOURCE_NOT_FOUND", 404)
            header = self._recipes(repo.recipes(store, [identifier], today)).get(
                identifier
            )
            warnings = []
            recipe = None
            if header:
                lines = repo.lines(store, header["id"])
                if len(lines) > 10485:
                    raise ReadFactError(True)
                values = []
                for line in lines:
                    if (
                        line["line_store"] != store
                        or line["ingredient_store"] != store
                        or line["unit"] != line["base_unit"]
                        or not line["name"]
                        or not line["unit"].strip()
                    ):
                        raise ReadFactError()
                    values.append(
                        dto.RecipeIngredient(
                            recipe_line_id=line["id"],
                            ingredient_id=line["ingredient_id"],
                            ingredient_name=line["name"],
                            ingredient_sku=line["sku"],
                            ingredient_active=line["active"],
                            expiry_tracking=line["expiry_tracking"],
                            base_unit=line["base_unit"],
                            quantity=decimal_text(line["quantity"], positive=True),
                            unit=line["unit"],
                        )
                    )
                if len(values) != header["line_count"]:
                    raise ReadFactError()
                recipe = dto.RecipeRead(
                    recipe_id=header["id"],
                    version=header["version"],
                    effective_from=header["effective_from"],
                    effective_to=header["effective_to"],
                    yield_quantity=decimal_text(
                        header["yield_quantity"], positive=True
                    ),
                    yield_unit=row["selling_unit"],
                    process_loss_rate=decimal_text(header["process_loss_rate"]),
                    ingredients=tuple(values),
                )
                if not values:
                    warnings.append(
                        issue(
                            "EMPTY_RECIPE",
                            "product",
                            identifier,
                            "recipe",
                            "Công thức hiện hành không có nguyên liệu",
                        )
                    )
            else:
                warnings.append(
                    issue(
                        "RECIPE_NOT_AVAILABLE",
                        "product",
                        identifier,
                        "recipe",
                        "Không có công thức hiệu lực tại ngày đọc",
                    )
                )
            return dto.ProductDetail(
                **self._product(row, basis["currency"]), recipe=recipe
            ), dict(warnings=tuple(warnings))

        return self._read(
            token,
            store,
            ("menu.read", "recipe.read", "ingredient.read"),
            True,
            request_id,
            build,
        )

    def _stock(self, row):
        if (
            row["invalid_lots"]
            or not row["base_unit"].strip()
            or not row["name"].strip()
        ):
            raise ReadFactError()
        reasons = [
            issue(
                "STOCK_COMPLETENESS_UNKNOWN",
                "ingredient",
                row["id"],
                "stock_completeness",
                "Chưa có khai báo đầy đủ tồn kho",
            ),
            issue(
                "THRESHOLD_UNKNOWN",
                "ingredient",
                row["id"],
                "threshold",
                "Chưa có ngưỡng sắp hết do Owner khai báo",
            ),
        ]
        if row["confirmed"]:
            reasons = [reason for reason in reasons if reason.code != "STOCK_COMPLETENESS_UNKNOWN"]
        if row["threshold"] is not None:
            reasons = [reason for reason in reasons if reason.code != "THRESHOLD_UNKNOWN"]
        if row["low"]:
            reasons.append(issue("LOW_STOCK", "ingredient", row["id"], "threshold", "Usable stock is at or below the Owner threshold"))
        for field, code, impact, error in [
            (
                "missing_required_expiry",
                "REQUIRED_EXPIRY_MISSING",
                "Lô dương thiếu hạn sử dụng bắt buộc",
                True,
            ),
            (
                "future_receipt",
                "RECEIVED_DATE_IN_FUTURE",
                "Ngày nhận lô nằm trong tương lai; không coi là hàng dùng được",
                True,
            ),
            (
                "missing_receipt",
                "MISSING_RECEIVED_DATE",
                "Chưa biết ngày nhận; không xác định được tuổi lô",
                False,
            ),
            (
                "missing_optional_expiry",
                "EXPIRY_UNKNOWN",
                "Lô không theo dõi hạn có expiry chưa biết",
                False,
            ),
            (
                "expired_count",
                "LOT_EXPIRED",
                "Có tồn vật lý hết hạn; GET không tự giảm số dư",
                False,
            ),
            (
                "near_count",
                "NEAR_EXPIRY",
                "Có lô dùng được hết hạn trong bảy ngày",
                False,
            ),
        ]:
            if row[field]:
                reasons.append(
                    issue(code, "ingredient", row["id"], field, impact, error=error)
                )
        unknown = bool(row["missing_required_expiry"] or row["future_receipt"])
        return dto.IngredientStock(
            ingredient_id=row["id"],
            name=row["name"],
            sku=row["sku"],
            ingredient_active=row["active"],
            unit=row["base_unit"],
            on_hand_quantity=decimal_text(row["physical"]),
            usable_quantity=None if unknown else decimal_text(row["usable"]),
            usable_known_quantity=decimal_text(row["usable"]),
            usable_availability="unknown" if unknown else "known",
            expired_quantity=decimal_text(row["expired"]),
            stock_completeness="CONFIRMED" if row["confirmed"] else "UNKNOWN",
            lot_count=row["lot_count"],
            positive_lot_count=row["positive_count"],
            nearest_expiry=row["nearest_expiry"],
            status=row["status"],
            status_reasons=tuple(reasons),
            low_stock_assessment=dto.LowStock(
                status=("low" if row["low"] else "ok") if row["assessed"] else "unknown",
                threshold=decimal_text(row["threshold"]) if row["threshold"] is not None else None, version=row["threshold_version"]
            ),
            near_expiry_lot_count=row["near_count"],
        )

    def inventory(
        self,
        token,
        store,
        request_id,
        *,
        q=None,
        statuses=(),
        identifiers=(),
        sort="name",
        limit=50,
        cursor=None
    ):
        def build(repo, basis, today, snapshot, identity, permissions):
            binding = [
                identity[0],
                str(store),
                "inventory",
                q,
                sorted(statuses),
                [str(x) for x in sorted(set(identifiers))],
                sort,
                limit,
            ]
            last = self._cursor(
                token,
                cursor,
                binding,
                snapshot,
                catalog=False,
                kind="date" if sort == "nearest_expiry" else "text",
            )
            rows, total, summary, missing = repo.inventory(
                store,
                today,
                fold_name(q) if q else None,
                statuses,
                identifiers,
                sort,
                last,
                limit,
            )
            rows, page = self._page(
                rows, total, limit, token, binding, snapshot, kind="text"
            )
            summary = dict(summary)
            return dto.InventoryList(
                summary=dto.InventorySummary(**summary),
                items=tuple(self._stock(r) for r in rows),
                missing_ingredient_ids=missing,
            ), dict(pagination=page)

        return self._read(
            token,
            store,
            ("inventory.read", "ingredient.read"),
            False,
            request_id,
            build,
        )

    @staticmethod
    def _lot(row, ingredient, today, first, currency, cost, snapshot):
        if row["unit"] != ingredient["base_unit"]:
            raise ReadFactError()
        quantity = decimal_text(row["on_hand_quantity"])
        return dto.LotRead(
            lot_id=row["id"],
            batch_code=row["lot_code"],
            quantity=quantity,
            unit=row["unit"],
            supplier_id=row["supplier_id"],
            received_date=row["received_date"],
            expiry_date=row["expiry_date"],
            status=lot_status(
                row["on_hand_quantity"],
                row["received_date"],
                row["expiry_date"],
                ingredient["expiry_tracking"],
                today,
            ),
            use_first=row["id"] == first,
            location=None,
            location_availability="unsupported",
            updated_at=row["updated_at"],
            version="lot-" + opaque([snapshot, str(row["id"])]),
            origin=row.get("origin") or "UNKNOWN",
            cost=dto.LotCost(
                availability=(
                    "forbidden"
                    if not cost
                    else "known" if row["unit_cost"] is not None else "unknown"
                ),
                unit_cost=(
                    decimal_text(row["unit_cost"], money=True)
                    if cost and row["unit_cost"] is not None
                    else None
                ),
                currency=currency,
            ),
        )

    def lot_read(
        self,
        token,
        store,
        identifier,
        request_id,
        *,
        detail=False,
        snapshot_id=None,
        limit=50,
        cursor=None
    ):
        def build(repo, basis, today, snapshot, identity, permissions):
            ingredient = repo.ingredient(store, identifier)
            if ingredient is None:
                raise AuthError("RESOURCE_NOT_FOUND", 404)
            binding = [
                identity[0],
                str(store),
                "lots",
                str(identifier),
                "expiry_date,batch_code",
                limit,
            ]
            last = self._cursor(
                token, cursor, binding, snapshot, catalog=False, kind="lots"
            )
            if snapshot_id is not None and snapshot_id != snapshot:
                raise AuthError("SNAPSHOT_NOT_AVAILABLE", 409)
            cost = "procurement.cost.read" in permissions
            rows, total, first = repo.lots(store, ingredient, today, last, limit, cost)
            rows, page = self._page(
                rows, total, limit, token, binding, snapshot, kind="lots"
            )
            lots = tuple(
                self._lot(
                    row, ingredient, today, first, basis["currency"], cost, snapshot
                )
                for row in rows
            )
            if detail:
                stocks, _, _, _ = repo.inventory(
                    store, today, None, (), (), "name", None, 1, one=identifier
                )
                result = dto.InventoryDetail(
                    **self._stock(stocks[0]).model_dump(),
                    lots=lots,
                    lots_page=dto.LotsPage(
                        next_cursor=page.next_cursor, total_count=total
                    ),
                    threshold_version=stocks[0]["threshold_version"] or "unconfigured-" + opaque(str(identifier))
                )
                return result, {}
            return dto.Lots(ingredient_id=identifier, items=lots), dict(pagination=page)

        return self._read(
            token,
            store,
            ("inventory.read", "ingredient.read"),
            False,
            request_id,
            build,
        )

    def movements(
        self,
        token,
        store,
        identifier,
        request_id,
        *,
        snapshot_id=None,
        limit=50,
        cursor=None
    ):
        def build(repo, basis, today, snapshot, identity, permissions):
            ingredient = repo.ingredient(store, identifier)
            if ingredient is None:
                raise AuthError("RESOURCE_NOT_FOUND", 404)
            binding = [
                identity[0],
                str(store),
                "movements",
                str(identifier),
                "-occurred_at",
                limit,
            ]
            last = self._cursor(
                token, cursor, binding, snapshot, catalog=False, kind="movements"
            )
            if snapshot_id is not None and snapshot_id != snapshot:
                raise AuthError("SNAPSHOT_NOT_AVAILABLE", 409)
            rows, total = repo.movements(store, identifier, last, limit)
            rows, page = self._page(
                rows, total, limit, token, binding, snapshot, kind="movements"
            )
            values = []
            for row in rows:
                if (
                    row["lot_store"] != store
                    or row["lot_ingredient"] != identifier
                    or row["unit"] != ingredient["base_unit"]
                ):
                    raise ReadFactError()
                amount = row["quantity_delta"]
                kind = row["movement_type"].lower()
                if (
                    amount == 0
                    or kind
                    not in {
                        "receipt",
                        "usage",
                        "waste",
                        "expired",
                        "count_correction",
                        "manual_adjustment",
                    }
                    or kind == "receipt"
                    and amount < 0
                    or kind in {"usage", "waste", "expired"}
                    and amount > 0
                ):
                    raise ReadFactError()
                if (row["reference_type"] is None) != (row["reference_id"] is None):
                    raise ReadFactError()
                reference = (
                    dto.MovementReference(
                        type=row["reference_type"], id=row["reference_id"]
                    )
                    if row["reference_type"] is not None
                    else None
                )
                values.append(
                    dto.MovementRead(
                        movement_id=row["id"],
                        lot_id=row["lot_id"],
                        batch_code=row["lot_code"],
                        kind=kind,
                        quantity_delta=decimal_text(amount, signed=True),
                        unit=row["unit"],
                        occurred_at=row["occurred_at"],
                        recorded_at=row["created_at"],
                        actor_user_id=row["actor_user_id"],
                        reason=row["note"],
                        reference=reference,
                        origin=row["movement_origin"] or "UNKNOWN",
                    )
                )
            return dto.Movements(ingredient_id=identifier, items=tuple(values)), dict(
                pagination=page
            )

        return self._read(
            token,
            store,
            ("inventory.read", "ingredient.read"),
            False,
            request_id,
            build,
        )
