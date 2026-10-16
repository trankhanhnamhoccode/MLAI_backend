"""Public Import facts feed existing BOM/inventory reads; history stays record-only."""
from datetime import date
from decimal import Decimal
import json
from pathlib import Path

import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models import Product, Ingredient, Recipe, RecipeLine, InventoryLot, InventoryMovement, ImportHistoryRecord, SupplierTerm, SalesDaily
from app.application.use_cases.readiness import ReadinessReads
from app.repositories.import_staging import capture_read_set
from app.domain.demand.bom import DemandPoint, DatedRecipe, RecipeLine as BOMLine, expand_dated_bom
from tests.integration.test_auth_public import env
from tests.integration.test_import_setup_stock import fresh_store, review_batch, complete
from tests.integration.test_import_commit import analyzed_files, commit
from tests.integration.test_import_staging import csv_source, previewed
from tests.integration.test_import_classification import confirm
from tests.integration.import_i5_evidence import i5_trace, save

ORACLE = json.loads((Path(__file__).parents[1] / 'fixtures/import_i5_synthetic_core.json').read_text(encoding='utf-8'))
pytestmark = pytest.mark.usefixtures('i5_trace')


def prepare_core(c, reverse=False):
    records = {schema: dict(row) for schema, row in ORACLE['records'].items()}
    records['opening_stock']['observed_at'] = c[0][4][0].isoformat()
    files = [(schema + '.csv', csv_source(schema, [row])) for schema, row in records.items()]
    if reverse:
        files.reverse()
    ident = analyzed_files(c, files)
    review_batch(c, ident, creations={key: (kind, facts) for key, (kind, facts) in ORACLE['creations'].items()})
    return ident


@pytest.mark.parametrize('reverse', [False, True])
def test_public_masters_recipe_opening_and_record_only_history_match_independent_values(fresh_store, monkeypatch, reverse):
    from app.infrastructure import import_suggestions
    monkeypatch.setattr(import_suggestions, 'suggest_sheet', lambda *a: pytest.fail('core fixture is offline'))
    c = fresh_store
    ident = prepare_core(c, reverse)
    with Session(c[0][1]) as fresh:
        for model in (Product, Ingredient, Recipe, InventoryLot, InventoryMovement, ImportHistoryRecord):
            assert fresh.scalar(select(func.count()).select_from(model)) == 0
    preview, done = complete(c, ident)
    with Session(c[0][1]) as fresh:
        product = fresh.scalar(select(Product))
        ingredient = fresh.scalar(select(Ingredient))
        recipe = fresh.scalar(select(Recipe))
        line = fresh.scalar(select(RecipeLine))
        lot = fresh.scalar(select(InventoryLot))
        move = fresh.scalar(select(InventoryMovement))
        assert product.sku == 'I5-COFFEE' and product.selling_unit == 'cup' and product.store_id == c[1].store_id
        assert ingredient.sku == 'I5-MILK' and ingredient.base_unit == 'g' and ingredient.store_id == c[1].store_id
        assert recipe.product_id == product.id and line.ingredient_id == ingredient.id
        assert recipe.yield_quantity == 10 and line.quantity == Decimal(ORACLE['expected']['whole_yield_ingredient'])
        assert recipe.process_loss_rate == Decimal(ORACLE['expected']['recipe_process_loss'])
        assert lot.ingredient_id == ingredient.id and lot.on_hand_quantity == Decimal(ORACLE['expected']['opening_quantity'])
        assert lot.received_date is None and lot.unit_cost is None
        assert move.quantity_delta == Decimal('1200') and move.reference_type == 'OPENING_STOCK'
        assert fresh.scalar(select(func.count()).select_from(InventoryMovement)) == ORACLE['expected']['movements']
        history = {r.domain: r.payload for r in fresh.scalars(select(ImportHistoryRecord))}
        assert set(history) == {'usage_history', 'purchase_history'}
        assert history['usage_history']['quantity'] == '20' and history['purchase_history']['quantity'] == '10'
        assert history['purchase_history']['received_date'] is None and history['purchase_history']['price_basis'] == 'PER_QUANTITY'
        assert fresh.scalar(select(func.count()).select_from(SupplierTerm)) == 0
        assert fresh.scalar(select(func.count()).select_from(SalesDaily)) == 0
        saved = DatedRecipe(recipe.id, product.id, recipe.effective_from, recipe.effective_to,
            recipe.yield_quantity, recipe.process_loss_rate, (BOMLine(ingredient.id, line.unit, line.quantity),))
        pid, iid = product.id, ingredient.id
    bom = expand_dated_bom((DemandPoint('BASE', pid, date(2026, 10, 10), Decimal(ORACLE['expected']['bom_servings'])),), (saved,))
    assert not bom.gaps and bom.totals[0].ingredient_id == iid
    assert bom.totals[0].quantity == Decimal(ORACLE['expected']['bom_required'])
    snapshot, _ = capture_read_set(c[0][1], c[1].store_id, ('recipes', 'opening_stock'))
    assert snapshot['inventory_lots'][0]['on_hand_quantity'] == ORACLE['expected']['opening_quantity']
    assert snapshot['recipe_lines'][0]['quantity'] == ORACLE['expected']['whole_yield_ingredient']
    c[0][5].app.state.readiness = ReadinessReads(c[0][2], None)
    response = c[0][5].get(f'/api/v1/stores/{c[1].store_id}/readiness', params={'actions': 'planning'})
    assert response.status_code == 200, response.text
    planning = response.json()['data']['actions'][0]
    assert not planning['can_execute'] and planning['blockers']
    save('core-' + str(reverse), dict(status='PASS', oracle=ORACLE, import_id=ident,
        actual_bom=str(bom.totals[0].quantity), stock_snapshot=snapshot['inventory_lots'],
        history=history, completion=done, readiness=response.json()['data']))


def test_requested_history_group_failure_rolls_back_all_imported_masters_and_other_groups(fresh_store, monkeypatch):
    from app.application.use_cases import import_history_write
    from app.application.contracts.auth import AuthError
    from app.models.import_staging import ImportJob, ImportBatch, ImportAudit
    from uuid import UUID
    c = fresh_store
    ident = prepare_core(c)
    preview = previewed(c, ident)
    reviewed = confirm(c, ident, preview)
    assert reviewed.status_code == 200, reviewed.text
    original = import_history_write.write_history
    flushed = []
    def fail_after_history(session, *args, **kwargs):
        original(session, *args, **kwargs)
        session.flush()
        flushed.append({model.__tablename__: session.scalar(select(func.count()).select_from(model))
                        for model in (Product, Ingredient, ImportHistoryRecord)})
        raise AuthError('PREVIEW_STALE', 409)
    monkeypatch.setattr(import_history_write, 'write_history', fail_after_history)
    accepted = commit(c, ident, preview, reviewed.json()['data']['import_revision'])
    assert accepted.status_code == 202, accepted.text
    c[2].run_one()
    assert flushed and all(n > 0 for n in flushed[0].values())
    with Session(c[0][1]) as fresh:
        counts = {model.__tablename__: fresh.scalar(select(func.count()).select_from(model))
                  for model in (Product, Ingredient, Recipe, RecipeLine, InventoryLot, InventoryMovement, ImportHistoryRecord)}
        assert all(n == 0 for n in counts.values())
        job = fresh.get(ImportJob, UUID(accepted.json()['data']['job_id']))
        assert job.status == 'failed' and job.error_json['code'] == 'PREVIEW_STALE'
        assert fresh.scalar(select(func.count()).select_from(ImportAudit).where(ImportAudit.kind == 'IMPORT_CANONICAL_COMMITTED')) == 0
        assert not fresh.get(ImportBatch, UUID(ident)).analysis_json.get('completion')
    save('core-atomic-failure', dict(status='PASS', import_id=ident, injected_after_flush=flushed,
         job_error='PREVIEW_STALE', canonical_counts_after_rollback=counts))
