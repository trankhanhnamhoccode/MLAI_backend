"""Coherent detached operational read-set for preview, never a canonical writer."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID
from sqlalchemy import func, select, text
from app.models import (
    Store,
    Product,
    Ingredient,
    Recipe,
    RecipeLine,
    SalesDaily,
    InventoryLot,
    InventoryMovement,
    Supplier,
    SupplierTerm,
)
from app.infrastructure.database.auth_session import auth_session
from app.application.contracts.auth import AuthError
from app.application.import_identity import content_digest

from app.models.operational_import import SupplierSourceRecord, TermSourceRecord, PayableFeeRecord, ScopeDeclarationRecord, InventoryReceiptRecord
from app.models.import_history import ImportHistoryRecord
from app.models.import_staging import ImportBatch, ImportFile, ImportAudit, ImportProfileVersion
from sqlalchemy.orm import Session


class ImportHistoryRepository:
    """Scoped history queries in the caller's authorized, transaction-owned Session."""
    def __init__(self, session: Session):
        self.session=session

    def latest_record_version(self, store_id: UUID, domain: str, source_system_key: str,
                              report_type: str, source_record_key: str) -> int | None:
        return self.session.scalar(select(func.max(ImportHistoryRecord.version)).where(
            ImportHistoryRecord.store_id == store_id,
            ImportHistoryRecord.domain == domain,
            ImportHistoryRecord.source_system_key == source_system_key,
            ImportHistoryRecord.report_type == report_type,
            ImportHistoryRecord.source_record_key == source_record_key))

    def store_timezone(self, store_id: UUID) -> str | None:
        return self.session.scalar(select(Store.timezone).where(Store.id==store_id))

    def batches(self, store_id: UUID, lower: datetime, upper: datetime, limit: int) -> tuple[ImportBatch, ...]:
        return tuple(self.session.scalars(select(ImportBatch).where(ImportBatch.store_id==store_id,
            ImportBatch.imported_at>=lower,ImportBatch.imported_at<upper)
            .order_by(ImportBatch.imported_at.desc(),ImportBatch.id.desc()).limit(limit)))

    def uploaded_files(self, batch_ids: list[UUID]) -> tuple[ImportFile, ...]:
        if not batch_ids:return ()
        return tuple(self.session.scalars(select(ImportFile).where(ImportFile.import_id.in_(batch_ids),
            ImportFile.upload_status=='uploaded').order_by(ImportFile.id)))

OPERATIONAL = (
    Product,
    Ingredient,
    Recipe,
    RecipeLine,
    SalesDaily,
    InventoryLot,
    InventoryMovement,
    Supplier,
    SupplierTerm,
    SupplierSourceRecord, TermSourceRecord, PayableFeeRecord, ScopeDeclarationRecord,
    InventoryReceiptRecord, ImportAudit, ImportHistoryRecord,
)
SCHEMA_TABLES = {
    "calendar_events": (ImportHistoryRecord,),
    "promotion_observations": (Product, ImportHistoryRecord),
    "usage_history": (Ingredient, ImportHistoryRecord),
    "purchase_history": (Ingredient, Supplier, ImportHistoryRecord),
    "sales": (Product, SalesDaily),
    "inventory_count": (Ingredient, InventoryLot, InventoryMovement, ImportAudit),
    "opening_stock": (Ingredient, Supplier, InventoryLot, InventoryMovement, InventoryReceiptRecord, ImportAudit),
    "recipes": (Product, Ingredient, Recipe, RecipeLine),
    "products": (Product,),
    "ingredients": (Ingredient,),
    "suppliers": (Supplier, SupplierSourceRecord),
    "supplier_terms": (Supplier, Ingredient, SupplierTerm, SupplierSourceRecord, TermSourceRecord, PayableFeeRecord),
    "payable_fees": (Supplier, SupplierTerm, SupplierSourceRecord, TermSourceRecord, PayableFeeRecord),
    "scope_declarations": tuple(m for m in OPERATIONAL if m is not ImportHistoryRecord),
    "scope_declarations.INVENTORY": (Ingredient, InventoryLot, InventoryMovement, ScopeDeclarationRecord),
    "scope_declarations.SALES_COVERAGE": (Product, SalesDaily, ScopeDeclarationRecord),
    "scope_declarations.PROCUREMENT_CONTEXT": (Supplier, Ingredient, ScopeDeclarationRecord),
}


def json_value(value):
    if isinstance(value, (UUID, date, datetime)):
        return str(value)
    if isinstance(value, Decimal):
        return format(value, "f")
    return value


def capture_read_set(engine, store_id, schemas=None):
    with engine.connect().execution_options(
        isolation_level="REPEATABLE READ", postgresql_readonly=True
    ) as connection:
        with auth_session(connection) as s:
            return read_set_in_session(s, store_id, schemas)


def read_set_in_session(s, store_id, schemas=None, *, fence=False):
    """Commit uses the caller transaction. Fences cover absent rows/S1 writers too."""
    chosen = tuple(sorted(set(schemas))) if schemas else tuple(sorted(SCHEMA_TABLES))
    selected = {model for schema in chosen for model in SCHEMA_TABLES[schema]}
    values = {model.__tablename__: [] for model in OPERATIONAL}
    values["_captured_schemas"] = chosen
    count = 0
    if fence:
        # Names are model constants, never request input. Short atomic commit only.
        for name in sorted(model.__tablename__ for model in selected):
            s.execute(text(f'LOCK TABLE "{name}" IN SHARE ROW EXCLUSIVE MODE'))
    row, xmin = s.execute(
        select(Store, text("xmin::text")).where(Store.id == store_id)
    ).one()
    values["stores"] = [
        {
            **{
                c.name: json_value(getattr(row, c.name))
                for c in Store.__table__.columns
            },
            "_row_version": xmin,
        }
    ]
    for model in OPERATIONAL:
        if model not in selected:
            continue
        query = select(model, text("xmin::text")).where(model.store_id == store_id)
        if model is ImportHistoryRecord:
            query = query.where(ImportHistoryRecord.domain.in_(set(chosen) & {
                'calendar_events','promotion_observations','usage_history','purchase_history'}))
        if model is ImportAudit:
            query = query.where(ImportAudit.kind == "IMPORT_CANONICAL_COMMITTED")
        rows = s.execute(
            query
            .order_by(*model.__table__.primary_key.columns)
            .limit(100001)
        ).all()
        count += len(rows)
        if count > 100000:
            raise AuthError("RESOURCE_LIMIT_EXCEEDED", 413)
        values[model.__tablename__] = [
            {
                **{
                    c.name: json_value(getattr(row, c.name))
                    for c in model.__table__.columns
                },
                "_row_version": xmin,
            }
            for row, xmin in rows
        ]
    if "sales" in chosen:
        audits = s.scalars(select(ImportAudit).where(
            ImportAudit.store_id == store_id,
            ImportAudit.kind == "IMPORT_CANONICAL_COMMITTED",
        ).order_by(ImportAudit.occurred_at, ImportAudit.id).limit(10001)).all()
        if len(audits) > 10000:
            raise AuthError("RESOURCE_LIMIT_EXCEEDED", 413)
        values["import_sales_sources"] = []
        for audit in audits:
            completion = audit.record_json.get('completion', {})
            legacy_scopes = {}
            if any('report_type' not in r for r in audit.record_json.get('sales_sources', ())):
                # Recover only immutable, same-Store pinned profile evidence, never
                # infer a historical report type from the incoming source declaration.
                for ref in completion.get('mapping_bindings', ()):
                    profile = s.get(ImportProfileVersion, (UUID(ref['profile_id']), ref['version']))
                    if profile is not None and profile.store_id == store_id and profile.content_digest == ref['content_digest']:
                        legacy_scopes[str(ref['sheet_id'])] = profile.spec_json['scope']
            for source in audit.record_json.get("sales_sources", []):
                if len(values["import_sales_sources"]) >= 100000:
                    raise AuthError("RESOURCE_LIMIT_EXCEEDED", 413)
                source = dict(source)
                if 'report_type' not in source:
                    candidates = {legacy_scopes[str(ref['source_location']['sheet_id'])]['report_type']
                        for ref in completion.get('canonical_references', ())
                        if ref.get('canonical_domain') == 'sales' and ref['canonical_id'] == source['canonical_id']
                        and str(ref['source_location']['sheet_id']) in legacy_scopes
                        and legacy_scopes[str(ref['source_location']['sheet_id'])]['source_system_key'] == source['source_system_key']}
                    source['report_type'] = next(iter(candidates)) if len(candidates) == 1 else None
                values["import_sales_sources"].append({**source, "audit_id": str(audit.id)})
    return values, content_digest(values)
