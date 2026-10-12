"""S4.6 fee/declaration identity and exact nested semantics, no database/provider."""
from uuid import uuid4
from copy import deepcopy
import pytest
from pydantic import ValidationError
from app.application.contracts.import_domains import FeeSource
from tests.unit.test_import_preview import case

def fee():
    return dict(source_fee_key="F1",scope="STORE_PROCUREMENT",effective_from="2026-10-11",effective_to=None,
        mode="PER_OFFER",coverage="UNKNOWN",currency="VND",components=[],covered_source_term_keys=[],
        covered_source_supplier_keys=[],evidence_reference="Explicit unknown fee coverage",reason="Record current knowledge")

def test_unknown_fee_is_explicit_not_implicit_zero_and_unknown_nested_identity_blocks():
    row=case("payable_fees",[fee()])[0]
    assert not row.blockers and "FEE_COVERAGE_UNKNOWN" in {n.code for n in row.warnings}
    value=fee();value["components"]=[dict(component_key="C1",label="Delivery",basis="PER_OFFER",source_term_key="UNKNOWN",
        source_supplier_key=None,amount="0",condition="WHEN_ORDERED")]
    row=case("payable_fees",[value])[0]
    assert "INVALID_FEE_REFERENCE" in {n.code for n in row.blockers}
    assert row.nested_provenance[0].path=="components[0]"

def fee_revision_case(amount,previous_amount):
    term=uuid4();value=fee()
    value["components"]=[dict(component_key="C1",label="Fixed fee",basis="PER_OFFER",source_term_key="T1",
        source_supplier_key=None,amount=amount,condition="WHEN_ORDERED")]
    previous={"domain":"payable_fees",**value,"components":[{**value["components"][0],"amount":previous_amount}]}
    ident=uuid4()
    snapshot=dict(payable_fee_records=[dict(id=str(ident),source_system_key="POS-A",source_record_key="F1",version=1,payload=previous,_row_version="3")],
        term_source_records=[dict(id=str(term),source_system_key="POS-A",source_record_key="T1")],
        supplier_terms=[dict(id=str(term),version=1,active=False,effective_from="2026-10-11",effective_to=None)])
    return value,previous,ident,snapshot

def test_fee_decimal_spelling_reuses_revision_without_rounding_or_historical_correction():
    value,previous,ident,snapshot=fee_revision_case("1.20","1.200")
    retained=deepcopy(snapshot)
    row=case("payable_fees",[value],snapshot)[0]
    assert not row.blockers and row.proposed_action=="NO_OP" and row.target_reserved_or_existing_id==ident
    assert row.before.components[0].amount=="1.200"
    assert row.after.components[0].amount=="1.20"
    assert snapshot==retained

def test_fee_22_decimal_input_is_blocked_without_rounding_or_rewriting_history():
    value,previous,ident,snapshot=fee_revision_case("1.0000000000000000000001","1.00000000000000000000010")
    retained=deepcopy(snapshot)
    row=case("payable_fees",[value],snapshot)[0]
    assert "INVALID_SOURCE_VALUE" in {n.code for n in row.blockers}
    assert row.after is None
    assert snapshot==retained

def test_fee_retained_evidence_preserves_exact_23_decimal_amount_without_write_bypass():
    value,previous,ident,snapshot=fee_revision_case("1.0000000000000000000001","1.00000000000000000000010")
    retained=deepcopy(previous)
    with pytest.raises(ValidationError):
        FeeSource.model_validate(previous)
    parsed=FeeSource.model_validate(previous,context={"retained_evidence":True})
    assert parsed.components[0].amount=="1.00000000000000000000010"
    assert parsed.model_dump(mode="json")==retained
    assert previous==retained

def test_same_inventory_declaration_key_cannot_change_ingredient_identity():
    one,two=uuid4(),uuid4()
    value=dict(source_declaration_key="D1",declaration=dict(kind="INVENTORY",ingredient_id=str(two),state="UNKNOWN",
        observed_at="2026-10-10T02:00:00Z",covered_lot_ids=[],evidence_reference="Current known scope"))
    snapshot=dict(ingredients=[dict(id=str(one),base_unit="l"),dict(id=str(two),base_unit="l")],
        scope_declaration_records=[dict(id=str(uuid4()),source_system_key="POS-A",source_record_key="D1",version=1,
            payload={**value,"declaration":{**value["declaration"],"ingredient_id":str(one)}},dependency_digest="old",_row_version="1")])
    row=case("scope_declarations",[value],snapshot)[0]
    assert "DECLARATION_IDENTITY_CONFLICT" in {n.code for n in row.blockers}

def test_duplicate_supplier_source_records_block_in_preview_before_double_create():
    from app.application.contracts import import_mapping as dto
    reservation=dto.EntityReservation(proposal_id=uuid4(),entity="supplier",source_business_key="S1",reserved_canonical_id=uuid4(),
        metadata=dict(name="Approved supplier",active=True),evidence_reference="Owner verified source identity",approval_revision="approved-1")
    value=dict(source_supplier_key="S1",name="Approved supplier",active=True)
    rows=case("suppliers",[value,value],entities=(reservation,))
    assert any("SOURCE_IDENTITY_CONFLICT" in {n.code for n in row.blockers} for row in rows)
