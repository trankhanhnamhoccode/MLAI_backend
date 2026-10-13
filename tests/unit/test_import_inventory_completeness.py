"""Missing, partial, confirmed zero and conflicting scopes stay distinct."""
from uuid import uuid4

from app.application.contracts.import_domains import InventoryDeclaration
from app.application.operational_import_facts import declaration_dependency, inventory_matches
from tests.unit.test_import_preview import NOW


def evidence(state, quantities, covered=None):
    ingredient = uuid4()
    lots = [dict(id=str(uuid4()), ingredient_id=str(ingredient), on_hand_quantity=q) for q in quantities]
    snapshot = dict(ingredients=[dict(id=str(ingredient), base_unit="l")], inventory_lots=lots)
    declaration = InventoryDeclaration(kind="INVENTORY", ingredient_id=ingredient, state=state, observed_at=NOW,
        covered_lot_ids=tuple(covered if covered is not None else [r["id"] for r in lots]) if state=="COMPLETE_CURRENT_LOTS" else (),
        evidence_reference="Explicit synthetic Owner observation")
    row = dict(dependency_digest=declaration_dependency(snapshot,declaration))
    return snapshot, ingredient, ((row,declaration),)


def test_missing_and_partial_are_unknown_but_explicit_empty_is_known():
    snap, ingredient, declarations = evidence("CONFIRMED_EMPTY", [])
    assert not inventory_matches(snap, (), ingredient, NOW)
    assert len(inventory_matches(snap, declarations, ingredient, NOW)) == 1
    snap, ingredient, declarations = evidence("COMPLETE_CURRENT_LOTS", ["12"], covered=[])
    assert not inventory_matches(snap, declarations, ingredient, NOW)


def test_confirmed_zero_retains_zero_lots_and_positive_balance_rejects_empty():
    snap, ingredient, declarations = evidence("CONFIRMED_EMPTY", ["0"])
    assert len(inventory_matches(snap, declarations, ingredient, NOW)) == 1
    snap, ingredient, declarations = evidence("CONFIRMED_EMPTY", ["12"])
    assert not inventory_matches(snap, declarations, ingredient, NOW)


def test_non_unique_or_changed_dependency_is_not_one_authoritative_scope():
    snap, ingredient, declarations = evidence("COMPLETE_CURRENT_LOTS", ["12"])
    assert len(inventory_matches(snap, declarations + declarations, ingredient, NOW)) == 2
    snap["inventory_lots"][0]["on_hand_quantity"] = "10"
    assert not inventory_matches(snap, declarations, ingredient, NOW)
