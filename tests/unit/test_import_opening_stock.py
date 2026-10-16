"""Opening observations are current balances, not receipts or counts of unknown lots."""
from uuid import uuid4

import pytest

from tests.unit.test_import_preview import case, NOW


def opening(ingredient, **changes):
    return dict(source_record_id="MILK-LOT-1", ingredient_id=str(ingredient), supplier_id=None,
        lot_code="LOT-1", quantity="12", unit="l", received_date=None,
        expiry_date="2026-10-25", unit_cost=None, currency="VND",
        observed_at=NOW.isoformat(), reason="Synthetic Owner opening observation", **changes)


def snapshot(ingredient):
    return dict(ingredients=[dict(id=str(ingredient), name="Milk", base_unit="l", expiry_tracking=True)])


def test_opening_plans_new_lot_and_keeps_unknown_received_date():
    ingredient = uuid4()
    row = case("opening_stock", [opening(ingredient)], snapshot(ingredient))[0]
    assert not row.blockers
    assert row.proposed_action == "CREATE_OPENING_STOCK"
    assert row.before is None and row.after.quantity == "12" and row.after.received_date is None
    assert row.target_reserved_or_existing_id == row.after.lot_id
    assert row.inventory_effect.quantity_delta == "12" and row.inventory_effect.origin == "OPENING_STOCK"
    assert {w.code for w in row.warnings} == {"MISSING_RECEIVED_DATE", "INVENTORY_COMPLETENESS_REQUIRES_DECLARATION"}


def test_wrong_opening_unit_is_not_inferred_or_filled_from_ingredient():
    ingredient=uuid4()
    data=opening(ingredient);data['unit']='kg'
    row,=case('opening_stock',[data],snapshot(ingredient))
    assert 'UNIT_MISMATCH' in {n.code for n in row.blockers}
    assert row.proposed_action=='BLOCKED' and row.after.unit=='kg'
    assert row.inventory_effect.movement_type is None  # Candidate effect is not an applied mutation.


@pytest.mark.parametrize("field,value,code", [
    ("quantity", "0", "INVALID_SOURCE_VALUE"), ("unit", None, "MISSING_REQUIRED_VALUE"),
    ("observed_at", "2026-10-10", "INVALID_SOURCE_VALUE"),
    ("expiry_date", None, "REQUIRED_EXPIRY_MISSING"), ("currency", "USD", "CURRENCY_MISMATCH"),
    ("received_date", "2026-10-26", "INVALID_SOURCE_VALUE")])
def test_opening_missing_or_invalid_fact_is_blocked(field, value, code):
    ingredient = uuid4()
    data = opening(ingredient); data[field] = value
    row = case("opening_stock", [data], snapshot(ingredient))[0]
    assert code in {n.code for n in row.blockers}


def test_same_physical_label_and_duplicate_source_block_every_row():
    ingredient = uuid4()
    rows = case("opening_stock", [opening(ingredient), opening(ingredient)], snapshot(ingredient))
    assert all({n.code for n in r.blockers} == {"DUPLICATE_OPENING_IDENTITY", "AMBIGUOUS_OPENING_LOT"} for r in rows)


def test_count_before_a_no_op_observation_is_stale():
    ingredient, lot = uuid4(), uuid4()
    data = dict(ingredient_id=str(ingredient), lot_id=str(lot), on_hand="10", unit="l",
        observed_at=NOW.isoformat(), reason="Synthetic older count")
    snap = snapshot(ingredient)
    snap["inventory_lots"] = [dict(id=str(lot), ingredient_id=str(ingredient), updated_at="2026-10-10T01:00:00+00:00", on_hand_quantity="12")]
    snap["import_audit"] = [dict(occurred_at="2026-10-10T04:00:00+00:00", record_json=dict(completion=dict(
        canonical_references=[dict(canonical_domain="inventory_count", canonical_id=str(lot))])))]
    row = case("inventory_count", [data], snap)[0]
    assert "STALE_STOCK_OBSERVATION" in {n.code for n in row.blockers}


def test_opening_replay_effect_keeps_current_balance_after_a_count():
    from app.application.contracts.import_domains import OpeningSource
    from app.application.import_opening_stock import fingerprint, receipt_semantics
    ingredient, lot = uuid4(), uuid4()
    data = opening(ingredient)
    snap = snapshot(ingredient)
    snap["inventory_lots"] = [dict(id=str(lot), ingredient_id=str(ingredient), on_hand_quantity="10")]
    snap["inventory_receipt_records"] = [dict(source_system_key="POS-A", source_record_key=data["source_record_id"],
        lot_id=str(lot), payload_digest=fingerprint(receipt_semantics(OpeningSource.model_validate(data), "POS-A")))]
    row = case("opening_stock", [data], snap)[0]
    assert row.proposed_action == "NO_OP" and row.after.quantity == "12"
    assert row.inventory_effect.before_quantity == row.inventory_effect.after_quantity == "10"
    assert row.inventory_effect.quantity_delta == "0" and row.inventory_effect.movement_type is None


def test_reviewed_physical_quantity_and_unit_price_preserve_value_and_raw():
    from app.application.contracts import import_mapping as dto
    ingredient = uuid4()
    data = opening(ingredient); data.update(quantity="1.5", unit="kg", unit_cost="100000")
    snap = snapshot(ingredient); snap["ingredients"][0]["base_unit"] = "g"
    conversion = dto.Conversion(kind="declared_conversion", from_unit="kg", to_unit="g",
        factor=dict(numerator="1000", denominator="1"), evidence_reference="Synthetic physical mass evidence")
    row = case("opening_stock", [data], snap, conversions=(conversion,))[0]
    assert not row.blockers
    assert row.after.quantity == "1500" and row.after.unit_cost == "100" and row.after.unit == "g"
    provenance = {p.field:p for p in row.provenance}
    assert provenance["quantity"].source_value == "1.5"
    assert provenance["unit_cost"].source_value == "100000"
    assert provenance["unit_cost"].applied_rule_ids == ("conversion:Synthetic physical mass evidence",)


def test_density_conversion_is_blocked_even_with_owner_declared_factor():
    from app.application.contracts import import_mapping as dto
    ingredient = uuid4()
    data = opening(ingredient); data["unit"] = "kg"
    conversion = dto.Conversion(kind="declared_conversion", from_unit="kg", to_unit="l",
        factor=dict(numerator="1", denominator="1"), evidence_reference="Unsupported density assertion")
    row = case("opening_stock", [data], snapshot(ingredient), conversions=(conversion,))[0]
    assert row.blockers[0].code == "INCOMPATIBLE_STOCK_UNIT_CONVERSION"


def test_reused_receipt_identity_with_changed_metadata_is_a_conflict():
    from app.application.contracts.import_domains import OpeningSource
    from app.application.import_opening_stock import fingerprint, receipt_semantics
    ingredient, lot = uuid4(), uuid4()
    data = opening(ingredient)
    snap = snapshot(ingredient)
    snap["inventory_receipt_records"] = [dict(source_system_key="POS-A", source_record_key=data["source_record_id"],
        lot_id=str(lot), payload_digest=fingerprint(receipt_semantics(OpeningSource.model_validate(data), "POS-A")))]
    data["lot_code"] = "CHANGED-LOT"
    row = case("opening_stock", [data], snap)[0]
    assert "RECEIPT_IDENTITY_CONFLICT" in {n.code for n in row.blockers}


def test_foreign_ingredient_uuid_is_not_accepted_without_scoped_binding():
    row = case("opening_stock", [opening(uuid4())], snapshot(uuid4()))[0]
    assert "UNKNOWN_INGREDIENT" in {n.code for n in row.blockers}
