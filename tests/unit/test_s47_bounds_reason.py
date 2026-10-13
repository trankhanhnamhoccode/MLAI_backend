from decimal import Decimal
from uuid import uuid4
from types import SimpleNamespace
import pytest
from pydantic import TypeAdapter, ValidationError
from app.application.contracts.import_scalars import Money, Quantity, Text
from app.application.contracts.common import MoneyDecimal
from app.application.contracts.import_mapping import CommitRequest, SalesContribution, SourceLocation, FieldProvenance
from app.application.import_descriptors import options
from app.application.import_commit import commit_rows
from app.application.contracts.auth import AuthError


def test_money_is_not_quantity_and_retained_legacy_evidence_is_explicit():
    exact = "999999999999999999.123456789012345678"
    assert TypeAdapter(Money).validate_python(exact) == exact
    assert TypeAdapter(MoneyDecimal).validate_python(exact) == Decimal(exact)
    assert str(TypeAdapter(MoneyDecimal).validate_python("0.1" + "0" * 80)) == "0.1"
    for value in ("1000000000000000000", "0.1234567890123456789"):
        assert TypeAdapter(Quantity).validate_python(value) == value
        with pytest.raises(ValidationError): TypeAdapter(Money).validate_python(value)
        with pytest.raises(ValidationError): TypeAdapter(MoneyDecimal).validate_python(value)
        assert TypeAdapter(Money).validate_python(value, context={"retained_evidence": True}) == value
    assert TypeAdapter(Text).validate_python("k" * 1000) == "k" * 1000
    with pytest.raises(ValidationError): TypeAdapter(Text).validate_python("k" * 1001)
    fields = {f.key: f for f in options()}
    assert "maxLength=1000" in fields["supplier_terms.source_term_key"].conditional_requirements
    assert any("{0,17}" in b for b in fields["supplier_terms.pack_cost"].conditional_requirements)


def test_missing_reason_checked_against_effective_actions(monkeypatch):
    body = CommitRequest(phase="commit", preview_id=uuid4(), preview_digest="x", confirm=True, resolutions=())
    for action in ("COUNT_CORRECTION", "MERGE_DISJOINT_SALES", "REPLACE_DAILY_TOTAL", "AMEND_TERM_PERIOD", "AMEND_FEE_PERIOD"):
        domain = {'COUNT_CORRECTION': 'inventory_count', 'AMEND_TERM_PERIOD': 'supplier_terms',
                  'AMEND_FEE_PERIOD': 'payable_fees'}.get(action, 'sales')
        contributions = (SalesContribution(source_system_key='POS-A', report_type='daily-sales',
            business_report_key='report', semantics='disjoint_contribution' if action == 'MERGE_DISJOINT_SALES' else 'daily_total',
            quantity='105', is_stockout=False, stockout_update='source',
            source_locations=(SourceLocation(file_id=uuid4(), sheet_id=uuid4(), record_number=2),),
            provenance=(FieldProvenance(field='quantity', source_value='105', origin='SOURCE_EXPLICIT'),)),) if domain == 'sales' else ()
        row = SimpleNamespace(canonical_domain=domain, after=SimpleNamespace(domain=domain),
            blockers=(), proposed_action=action, sales_contributions=contributions)
        import app.application.import_commit as module
        monkeypatch.setattr(module.dto.PreviewRow, "model_validate", lambda r: r)
        preview = SimpleNamespace(content_json=dict(rows=[row], summary=dict(blockers=[])))
        with pytest.raises(AuthError, match="COMMIT_REASON_REQUIRED"):
            commit_rows(preview, body)
    with pytest.raises(ValidationError):
        CommitRequest(phase="commit", preview_id=uuid4(), preview_digest="x", confirm=True, resolutions=(), reason="  ")
