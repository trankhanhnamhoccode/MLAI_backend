"""Private canonical operational evidence; never exposed as a public API bag."""
from decimal import Decimal
from fractions import Fraction
from uuid import UUID
from typing import Literal
from pydantic import Field,model_validator,model_serializer,AwareDatetime
from app.application.contracts.common import Contract,Nonblank,NonnegativeDecimal,PositiveDecimal
from app.application.contracts.import_domains import TermSource,FeeSource,DeclarationSource


class TermEvidence(Contract):
    term_id: UUID
    version: int=Field(gt=0)
    source_system_key: Nonblank
    source_record_key: Nonblank
    payload: TermSource


class SupplierEvidence(Contract):
    supplier_id: UUID
    source_system_key: Nonblank
    source_record_key: Nonblank


class FeeEvidence(Contract):
    id: UUID
    version: int=Field(gt=0)
    source_system_key: Nonblank
    source_record_key: Nonblank
    payload: FeeSource


class DeclarationEvidence(Contract):
    id: UUID
    version: int=Field(gt=0)
    source_system_key: Nonblank
    source_record_key: Nonblank
    dependency_digest: Nonblank
    payload: DeclarationSource


class BoundEvidence(Contract):
    term_id: UUID
    effective_budget: NonnegativeDecimal
    budget_version: Nonblank
    pack_cost: NonnegativeDecimal
    pack_size: PositiveDecimal
    source_maximum_quantity: NonnegativeDecimal | None
    declared_limit_quantity: NonnegativeDecimal | None
    maximum_packs: int=Field(ge=0,strict=True)

    @model_validator(mode='after')
    def exact_derivation(self):
        bounds=[]
        if self.pack_cost:bounds.append(int(Fraction(self.effective_budget)//Fraction(self.pack_cost)))
        bounds.extend(int(Fraction(q)//Fraction(self.pack_size)) for q in (self.source_maximum_quantity,self.declared_limit_quantity) if q is not None)
        if not bounds or min(bounds)!=self.maximum_packs:raise ValueError('Bound evidence differs from exact captured finite derivation')
        return self


class SourceConfirmation(Contract):
    entity: Literal['supplier_term','supplier','fee','declaration']
    entity_id: UUID
    source_system_key: Nonblank
    source_record_key: Nonblank
    provenance_digest: Nonblank
    actor_id: UUID | None
    confirmed_at: AwareDatetime | None
    audit_id: UUID | None

    @model_validator(mode='after')
    def known_audit(self):
        if any(v is not None for v in (self.actor_id,self.confirmed_at,self.audit_id)) and not all(
                v is not None for v in (self.actor_id,self.confirmed_at,self.audit_id)):
            raise ValueError('Confirmation actor/time/audit must come from one complete retained source proof')
        return self


class PlanningSourceEvidence(Contract):
    terms: tuple[TermEvidence,...]
    suppliers: tuple[SupplierEvidence,...]
    fees: tuple[FeeEvidence,...]
    declarations: tuple[DeclarationEvidence,...]
    bounds: tuple[BoundEvidence,...]
    observed_history_product_ids: tuple[UUID,...]
    confirmations: tuple[SourceConfirmation,...] | None = None

    @model_serializer(mode='wrap')
    def preserve_legacy(self,handler):
        result=handler(self)
        if result.get('confirmations') is None:result.pop('confirmations',None)
        return result
