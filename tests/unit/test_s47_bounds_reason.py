from decimal import Decimal
from uuid import uuid4
from types import SimpleNamespace
import pytest
from pydantic import TypeAdapter, ValidationError
from app.application.contracts.import_scalars import Money, Quantity, Text
from app.application.contracts.common import MoneyDecimal
from app.application.contracts.import_mapping import CommitRequest
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
        row = SimpleNamespace(canonical_domain="sales", after=SimpleNamespace(domain="sales"),
            blockers=(), proposed_action=action)
        import app.application.import_commit as module
        monkeypatch.setattr(module.dto.PreviewRow, "model_validate", lambda r: r)
        preview = SimpleNamespace(content_json=dict(rows=[row], summary=dict(blockers=[])))
        with pytest.raises(AuthError, match="COMMIT_REASON_REQUIRED"):
            commit_rows(preview, body)
    with pytest.raises(ValidationError):
        CommitRequest(phase="commit", preview_id=uuid4(), preview_digest="x", confirm=True, resolutions=(), reason="  ")
