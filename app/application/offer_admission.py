"""Recognize absent offer-local facts without treating invalid data as absence."""
from collections.abc import Mapping
from pydantic import ValidationError
from app.application.contracts.offer_admission import MissingOfferField, OfferOmission, OmissionReason
from app.application.contracts.supplier import SupplierTermResult

MISSING_FIELDS: tuple[MissingOfferField,...] = (
    'pack_cost','pack_size_base_quantity','minimum_order_packs','lead_time_days','unit')


def missing_offer_fields(values: Mapping[str,object],error: ValidationError) -> tuple[MissingOfferField,...]:
    """Only absent/null scalar facts, never blanks, negatives, conflicts or scope."""
    missing=tuple(field for field in MISSING_FIELDS if values.get(field) is None)
    return missing if missing and all(e['loc'] and e['loc'][0] in missing for e in error.errors()) else ()


def term_from_snapshot(row: Mapping[str,object]) -> SupplierTermResult:
    return SupplierTermResult.model_validate({k:v for k,v in row.items() if k in SupplierTermResult.model_fields})


def omission(row: Mapping[str,object],reason: OmissionReason,fields: tuple[MissingOfferField,...]=()) -> OfferOmission:
    return OfferOmission(store_id=row['store_id'],term_id=row['id'],supplier_id=row['supplier_id'],
        ingredient_id=row['ingredient_id'],version=row['version'],effective_from=row['effective_from'],
        effective_to=row['effective_to'],reason=reason,missing_fields=fields,
        source_reference=f"SupplierTerm/{row['id']}/version/{row['version']}")
