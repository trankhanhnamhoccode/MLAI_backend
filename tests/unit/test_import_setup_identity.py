"""Whole-batch identity must not depend on source iteration order."""
from uuid import uuid4

import pytest

from app.application.contracts import import_mapping as dto
from app.application.contracts.import_domains import ProductSource, SalesSource
from app.application.import_dependencies import finalize_dependencies
from app.application.import_dependencies import order_dependencies
from app.application.contracts.auth import AuthError


def row(value, refs, action="INSERT"):
    return dto.PreviewRow(row_id=uuid4(), source_location=dto.SourceLocation(
        file_id=uuid4(), sheet_id=uuid4(), row_number=4), classification="NEW",
        proposed_action=action, entity_refs=refs, before=None, after=value, provenance=())


@pytest.mark.parametrize("reverse", [False, True])
def test_master_row_dependency_is_explicit_in_both_orders(reverse):
    ident = uuid4()
    ref = dto.EntityRef(entity="product", canonical_id=ident)
    master = row(ProductSource(source_business_key="COFFEE", name="Coffee",
        selling_unit="cup", sku="C1", price=None, active=True), (ref,), "CREATE_PRODUCT")
    sale = row(SalesSource(product_id=ident, sales_date="2026-10-09",
        quantity="3", unit="cup", business_report_key="DAY-1"), (ref,))
    rows = finalize_dependencies((sale, master) if reverse else (master, sale))
    assert next(r for r in rows if r.row_id == sale.row_id).dependencies == (master.row_id,)
    assert not any(r.blockers for r in rows)


def test_duplicate_creation_blocks_every_candidate_and_consumer():
    ident = uuid4()
    ref = dto.EntityRef(entity="product", canonical_id=ident)
    value = ProductSource(source_business_key="COFFEE", name="Coffee",
        selling_unit="cup", sku="C1", price=None, active=True)
    a, b = row(value, (ref,), "CREATE_PRODUCT"), row(value, (ref,), "CREATE_PRODUCT")
    sale = row(SalesSource(product_id=ident, sales_date="2026-10-09",
        quantity="3", unit="cup", business_report_key="DAY-1"), (ref,))
    rows = finalize_dependencies((sale, b, a))
    assert all(r.proposed_action == "BLOCKED" for r in rows)
    assert all(r.blockers[0].source_location.row_number == 4 for r in rows)


def test_duplicate_sku_distinct_approved_ids_blocks_consumers():
    a_id, b_id = uuid4(), uuid4()
    value = ProductSource(source_business_key="A", name="Same display name", selling_unit="cup", sku="SAME", price=None, active=True)
    a = row(value, (dto.EntityRef(entity="product", canonical_id=a_id),), "CREATE_PRODUCT")
    b = row(value.model_copy(update={"source_business_key":"B"}), (dto.EntityRef(entity="product", canonical_id=b_id),), "CREATE_PRODUCT")
    assert all(r.blockers[0].code == "ENTITY_IDENTITY_CONFLICT" for r in finalize_dependencies((b,a)))


def test_same_name_distinct_skus_remain_distinct_entities():
    value = ProductSource(source_business_key="A", name="Coffee", selling_unit="cup", sku="A", price=None, active=True)
    a = row(value, (dto.EntityRef(entity="product", canonical_id=uuid4()),), "CREATE_PRODUCT")
    b = row(value.model_copy(update={"source_business_key":"B", "sku":"B"}), (dto.EntityRef(entity="product", canonical_id=uuid4()),), "CREATE_PRODUCT")
    assert not any(r.blockers for r in finalize_dependencies((a,b)))


def test_topological_order_and_cycle_guard():
    ref = dto.EntityRef(entity="product", canonical_id=uuid4())
    value = SalesSource(product_id=ref.canonical_id, sales_date="2026-10-09", quantity="1", unit="cup", business_report_key="R")
    a, b = row(value, (ref,)), row(value, (ref,))
    b = b.model_copy(update={"dependencies":(a.row_id,)})
    assert order_dependencies((b,a)) == (a,b)
    with pytest.raises(AuthError, match="SOURCE_IDENTITY_CONFLICT"):
        order_dependencies((a.model_copy(update={"dependencies":(b.row_id,)}),b))
