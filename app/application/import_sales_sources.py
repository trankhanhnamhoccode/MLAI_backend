"""Deterministic sales report revision handling from captured immutable evidence."""

from decimal import Decimal
from fractions import Fraction


def sources_for(snapshot, product_id, day):
    return [r for r in snapshot.get("import_sales_sources", ())
            if r["product_id"] == str(product_id) and r["sales_date"] == str(day)]


def latest_source(history, system, report):
    matches = [r for r in history if r["source_system_key"] == system
               and r["business_report_key"] == report]
    return max(matches, key=lambda r: r["source_revision"], default=None)


def classify_sales(value, current, spec, snapshot):
    """Returns aggregate target/action/classification/blocker; never chooses grain."""
    history = sources_for(snapshot, value.product_id, value.sales_date)
    old = latest_source(history, spec.scope.source_system_key, value.business_report_key)
    before = Decimal(current["quantity"]) if current else Decimal(0)
    incoming = Decimal(value.quantity)
    semantics = spec.sales_semantics
    if old and old["semantics"] != semantics:
        return value.quantity, "BLOCKED", "CONFLICT", "SALES_OVERLAP_UNRESOLVED"
    # Do not claim retained sources still explain a total changed by another writer.
    last = max(history, key=lambda r: r["canonical_revision"], default=None)
    if last and (not current or Decimal(last["canonical_quantity"]) != before):
        return value.quantity, "BLOCKED", "CONFLICT", "SALES_OVERLAP_UNRESOLVED"
    if history and any(r["semantics"] != semantics for r in history):
        return value.quantity, "BLOCKED", "CONFLICT", "SALES_OVERLAP_UNRESOLVED"
    if old and Decimal(old["source_quantity"]) == incoming:
        return str(before), "NO_OP", "UNCHANGED", None
    if semantics == "daily_total":
        if current and before == incoming:
            return value.quantity, "NO_OP", "UNCHANGED", None
        return value.quantity, "REPLACE_DAILY_TOTAL" if current else "INSERT", "CHANGED" if current else "NEW", None
    if old:
        target = Fraction(before) - Fraction(Decimal(old["source_quantity"])) + Fraction(incoming)
        if target < 0:
            return value.quantity, "BLOCKED", "CONFLICT", "SALES_OVERLAP_UNRESOLVED"
        from app.application.import_preview import exact_text
        return exact_text(target), "REPLACE_DAILY_TOTAL", "CHANGED", None
    if current:
        from app.application.import_preview import exact_text
        return exact_text(Fraction(before) + Fraction(incoming)), "MERGE_DISJOINT_SALES", "CHANGED", None
    return value.quantity, "INSERT", "NEW", None
