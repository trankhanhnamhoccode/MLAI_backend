"""Versioned captured offer omissions; no canonical facts or search-policy defaults."""
from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator
from app.application.contracts.common import Contract, Nonblank

MissingOfferField = Literal['pack_cost','pack_size_base_quantity','minimum_order_packs','lead_time_days','unit','shelf_life_days']
OmissionReason = Literal['OFFER_BOUND_UNKNOWN','SUPPLIER_TERM_FACT_UNAVAILABLE']


class OfferOmission(Contract):
    store_id: UUID
    term_id: UUID
    supplier_id: UUID
    ingredient_id: UUID
    version: int = Field(gt=0, strict=True)
    effective_from: date
    effective_to: date | None
    reason: OmissionReason
    missing_fields: tuple[MissingOfferField, ...] = ()
    source_reference: Nonblank

    @model_validator(mode='after')
    def meaningful(self):
        if (self.reason=='SUPPLIER_TERM_FACT_UNAVAILABLE') != bool(self.missing_fields):
            raise ValueError('Missing facts require explicit missing fields; missing bound is separate')
        if len(set(self.missing_fields))!=len(self.missing_fields):
            raise ValueError('Duplicate missing field')
        if self.effective_to is not None and self.effective_to<self.effective_from:
            raise ValueError('Omission effective dates conflict')
        return self


class OfferAdmission(Contract):
    policy: Literal['offer_eligibility/1'] = 'offer_eligibility/1'
    proof_scope: Literal['CAPTURED_ELIGIBLE_OFFERS_ONLY'] = 'CAPTURED_ELIGIBLE_OFFERS_ONLY'
    omissions: tuple[OfferOmission, ...]

    @model_validator(mode='after')
    def distinct(self):
        if len({o.term_id for o in self.omissions})!=len(self.omissions):
            raise ValueError('Duplicate omitted offer identity')
        object.__setattr__(self,'omissions',tuple(sorted(self.omissions,key=lambda o:o.term_id)))
        return self
