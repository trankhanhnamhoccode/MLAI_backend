from datetime import datetime, timezone, date
from types import SimpleNamespace
from uuid import UUID

from app.application.readiness_evaluation import evaluate


def readiness(flags):
    pid, store = UUID(int=1), UUID(int=2)
    snapshot = {key: [] for key in ('ingredients', 'recipes', 'recipe_lines', 'inventory_lots',
        'inventory_movements', 'suppliers', 'supplier_terms', 'supplier_source_records',
        'term_source_records', 'payable_fee_records', 'scope_declaration_records', 'business_constraints')}
    snapshot.update(stores=[dict(id=str(store), timezone='Asia/Ho_Chi_Minh')],
        products=[dict(id=str(pid), selling_unit='cup', active=True)],
        sales_daily=[dict(product_id=str(pid), sales_date=f'2026-10-{day:02}', quantity='0', is_stockout=flag)
                     for day, flag in enumerate(flags, 1)])
    facts = SimpleNamespace(snapshot=snapshot, defaults=None, cap=None, saved=(),
        serving=SimpleNamespace(version='configured'))
    result = evaluate(facts, store, datetime(2026, 10, 10, tzinfo=timezone.utc), date(2026, 10, 10),
        ('forecast',), ('planning.context.read', 'sales.read'))
    return result


def test_missing_vs_censored_blocker_and_unknown_quality_warning():
    missing, censored, unknown = (readiness(flags) for flags in ((), (True,), (None,)))
    assert missing.scope_estimate.estimated_computable_product_count == 0
    assert 'PRODUCT_HISTORY_MISSING' in {w.code for w in missing.actions[0].warnings}
    assert 'CENSORED_HISTORY_NOT_USABLE' in {b.code for b in censored.actions[0].blockers}
    assert unknown.scope_estimate.estimated_computable_product_count == 1
    assert unknown.actions[0].can_execute
    assert 'STOCKOUT_UNKNOWN' in {w.code for w in unknown.actions[0].warnings}


def test_known_uncensored_zero_ready_without_unknown_stockout():
    result = readiness((False,))
    assert result.actions[0].can_execute
    assert 'STOCKOUT_UNKNOWN' not in {w.code for w in result.actions[0].warnings}
