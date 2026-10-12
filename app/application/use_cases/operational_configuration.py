"""Transaction-owned typed source/config writers; no engine or provider calls."""
from uuid import UUID
from hashlib import sha256
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.application.contracts.import_domains import SupplierSource, TermSource, FeeSource, DeclarationSource
from app.application.contracts.supplier import CreateSupplierTermInput
from app.application.contracts.auth import AuthError
from app.application._validation import require_store
from app.application.use_cases.supplier import SupplierTermUseCases
from app.models import Supplier, SupplierTerm
from app.models.operational_import import SupplierSourceRecord, TermSourceRecord, PayableFeeRecord, ScopeDeclarationRecord
from app.repositories.supplier import SupplierRepository


class OperationalConfiguration:
    def __init__(self, session: Session, store_id: UUID):
        self.session, self.store_id = session, store_id

    def supplier(self, value: SupplierSource, ident: UUID, system: str, provenance: dict, *, create: bool):
        require_store(self.session, self.store_id)
        repo = SupplierRepository(self.session)
        if create:
            repo.add_supplier(self.store_id, Supplier(id=ident, store_id=self.store_id, name=value.name, active=value.active))
            self.session.flush()
        else:
            existing = repo.get_supplier(self.store_id, ident)
            if existing is None or (existing.name, existing.active) != (value.name, value.active):
                raise AuthError("SUPPLIER_METADATA_CONFLICT", 409)
        source_hash=sha256(value.source_supplier_key.encode()).hexdigest()
        key = self.store_id, system, source_hash
        old = self.session.get(SupplierSourceRecord, key)
        if old and (old.supplier_id != ident or old.source_record_key != value.source_supplier_key):
            raise AuthError("SOURCE_IDENTITY_CONFLICT", 409)
        if not old:
            self.session.add(SupplierSourceRecord(store_id=self.store_id,source_system_key=system,
                source_record_key=value.source_supplier_key,source_record_hash=source_hash,supplier_id=ident,provenance=provenance))
        self.session.flush()

    def term(self, value: TermSource, ident: UUID, system: str, provenance: dict):
        version = (self.session.scalar(select(func.max(SupplierTerm.version)).where(
            SupplierTerm.store_id == self.store_id, SupplierTerm.supplier_id == value.supplier_id,
            SupplierTerm.ingredient_id == value.ingredient_id)) or 0) + 1
        data = value.model_dump(exclude={"domain","source_term_key","currency","maximum_order_base_quantity"})
        result = SupplierTermUseCases(self.session).create_in_transaction(
            CreateSupplierTermInput(store_id=self.store_id,version=version,**data),reserved_id=ident)
        self.session.add(TermSourceRecord(id=result.id,store_id=self.store_id,source_system_key=system,
            source_record_key=value.source_term_key,payload=value.model_dump(mode="json"),provenance=provenance))
        self.session.flush()
        return result

    def close_term(self, ident: UUID, effective_to):
        old = self.session.scalar(select(SupplierTerm).where(SupplierTerm.id==ident,SupplierTerm.store_id==self.store_id).with_for_update())
        if old is None or old.effective_to is not None or effective_to < old.effective_from:
            raise AuthError("TERM_AMENDMENT_CONFLICT",409)
        old.effective_to=effective_to
        self.session.flush()

    def fee(self, value: FeeSource, ident: UUID, system: str, provenance: dict, references: dict):
        version=(self.session.scalar(select(func.max(PayableFeeRecord.version)).where(
            PayableFeeRecord.store_id==self.store_id,PayableFeeRecord.source_system_key==system,
            PayableFeeRecord.source_record_key==value.source_fee_key)) or 0)+1
        self.session.add(PayableFeeRecord(id=ident,store_id=self.store_id,source_system_key=system,
            source_record_key=value.source_fee_key,source_record_hash=sha256(value.source_fee_key.encode()).hexdigest(),version=version,payload=value.model_dump(mode="json"),
            resolved_references=references,provenance=provenance));self.session.flush()

    def declaration(self,value: DeclarationSource,ident: UUID,system: str,provenance: dict,dependency: str):
        version=(self.session.scalar(select(func.max(ScopeDeclarationRecord.version)).where(
            ScopeDeclarationRecord.store_id==self.store_id,ScopeDeclarationRecord.source_system_key==system,
            ScopeDeclarationRecord.source_record_key==value.source_declaration_key)) or 0)+1
        self.session.add(ScopeDeclarationRecord(id=ident,store_id=self.store_id,source_system_key=system,
            source_record_key=value.source_declaration_key,source_record_hash=sha256(value.source_declaration_key.encode()).hexdigest(),version=version,payload=value.model_dump(mode="json"),
            dependency_digest=dependency,provenance=provenance));self.session.flush()
