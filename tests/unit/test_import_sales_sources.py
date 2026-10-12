"""Exact source revisions do not double count or lose decimal precision."""
from types import SimpleNamespace
from uuid import uuid4
from datetime import date
from app.application.contracts.import_domains import SalesSource
from app.application.import_sales_sources import classify_sales


def test_merge_preserves_more_than_decimal_context_precision():
    value = SalesSource(product_id=uuid4(), sales_date=date(2026, 10, 9), quantity="0.000000000000000000001",
                        unit="cup", business_report_key="report-new")
    spec = SimpleNamespace(scope=SimpleNamespace(source_system_key="POS"), sales_semantics="disjoint_contribution")
    target, action, classification, blocker = classify_sales(value, {"quantity": "1000.123456789012345678901"}, spec, {})
    assert (target, action, classification, blocker) == ("1000.123456789012345678902", "MERGE_DISJOINT_SALES", "CHANGED", None)


def test_recorded_contribution_revision_replaces_only_its_old_amount():
    value = SalesSource(product_id=uuid4(), sales_date=date(2026, 10, 9), quantity="110", unit="cup", business_report_key="report")
    spec = SimpleNamespace(scope=SimpleNamespace(source_system_key="POS"), sales_semantics="disjoint_contribution")
    source = dict(product_id=str(value.product_id), sales_date=str(value.sales_date), source_system_key="POS",
                  business_report_key="report", source_revision=1, canonical_revision=1,
                  source_quantity="105", canonical_quantity="205", semantics="disjoint_contribution")
    target, action, classification, blocker = classify_sales(value, {"quantity": "205"}, spec, {"import_sales_sources": [source]})
    assert (target, action, classification, blocker) == ("210", "REPLACE_DAILY_TOTAL", "CHANGED", None)
