"""Continuous I1–I4 public acceptance with independent synthetic cell/value oracle."""
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.application.contracts.import_mapping import SuggestionDiagnostic
from app.application.contracts.import_suggestions import SheetSuggestion
from app.application.contracts.forecast_execution import ForecastExecutionInput
from app.application.use_cases.forecast_execution import ForecastExecutionUseCases
from app.domain.permissions import PERMISSIONS
from app.models import Product, SalesDaily, InventoryLot, InventoryMovement
from app.models.import_staging import ImportAudit, ImportBatch, ImportJob, ImportProfileVersion
from tests.integration.test_auth_public import env
from tests.integration.test_staff_public import staff_env, owner_session
from tests.integration.test_import_completion_workflow import staff_context, switch_staff
from tests.integration.test_import_staging import analyzed, post, previewed
from tests.integration.test_import_rule_review import summary, declare_context
from tests.integration.test_import_classification import listing, mapping, confirm
from tests.integration.test_import_commit import commit, finished
from tests.integration.test_mapping_submissions import submit
from tests.integration.import_i5_evidence import i5_trace, save

ORACLE = json.loads((Path(__file__).parents[1] / 'fixtures/import_i5_synthetic.json').read_text(encoding='utf-8'))
pytestmark = pytest.mark.usefixtures('i5_trace')


def source(product, quantity):
    return (','.join(ORACLE['headers']) + '\n' + ','.join([ORACLE['sales_date'], str(product), quantity,
            ORACLE['unit'], ORACLE['report_key']]) + '\n').encode()


def no_import_facts(context):
    with Session(context[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(SalesDaily)) == 0
        assert fresh.scalar(select(func.count()).select_from(Product)) == 1  # Explicit prerequisite only.
        assert fresh.scalar(select(func.count()).select_from(InventoryLot)) == 0
        assert fresh.scalar(select(func.count()).select_from(InventoryMovement)) == 0


@pytest.mark.parametrize('provider', ['proposal', 'outage'])
def test_continuous_suggestions_staff_review_commit_reuse_correction_lineage_and_readiness(
        staff_env, monkeypatch, provider):
    from app.infrastructure import import_suggestions as gateway
    ctx = staff_env
    staff = staff_context(ctx, PERMISSIONS)
    # Match the supported synthetic auth clock at this composition boundary;
    # availability stays explicit/unavailable, no readiness facts are seeded.
    from app.application.use_cases.readiness import ReadinessReads
    ctx[0][5].app.state.readiness = ReadinessReads(ctx[0][2], None)
    staff[2].settings = staff[2].settings.model_copy(update={
        'import_llm_suggestions_enabled': True, 'openrouter_api_key': SecretStr('I5-SYNTHETIC-ONLY'),
        'import_semantic_sheet_limit': 1})
    calls = []
    def suggest(settings, sheet, raw, filename, rule, selected, diagnostics):
        assert ctx[0][1].pool.checkedout() == 0
        calls.append(str(sheet.sheet_id))
        assert {c['column_index'] for row in raw['rows'] for c in row['cells']} == {2}
        assert raw['rows'][0]['cells'][0]['raw'] == ORACLE['first_quantity']
        diagnostics.append(SuggestionDiagnostic(status='proposed' if provider == 'proposal' else 'unavailable',
            model=settings.openrouter_mapping_model, attempts=1, failure_code=None if provider == 'proposal' else 'LLM_UNAVAILABLE'))
        if provider == 'outage':
            return None, 'LLM_UNAVAILABLE'
        return SheetSuggestion.model_validate(dict(version='sheet_suggestion/1', sheet_type='sales',
            confidence=0.8, warnings=[], columns=[dict(source_column_index=c['source_column_index'],
                target_field='sales.quantity' if c['source_column_index'] == 2 else c['target_field'],
                confidence=0.8, reason='I5 fake proposal, explicit review still required') for c in rule['columns']])), None
    monkeypatch.setattr(gateway, 'suggest_sheet', suggest)
    ident = analyzed(staff, source(staff[4], ORACLE['first_quantity']))
    assert calls == []  # I03 discovery is offline even with valid effective config.
    current = declare_context(staff, ident, ORACLE['source_context'])
    assert not current['can_preview'] and not current['completion_guidance']['profiles'][0]['review_ready']
    fields = ctx[0][5].get('/api/v1/imports/' + ident + '/sheets/' + current['sheets'][0]['sheet_id'] + '/field-options')
    assert fields.status_code == 200, fields.text
    read = ctx[0][5].get('/api/v1/imports/' + ident).json()['data']
    body = dict(phase='semantic_suggestions', mapping_revision=current['mapping_revision'],
                sheet_ids=[current['sheets'][0]['sheet_id']])
    key = str(uuid4())
    accepted = post(staff, '/imports/' + ident + '/process', body, key=key, match=read['import_revision'])
    assert accepted.status_code == 202, accepted.text
    staff[2].run_one()
    assert post(staff, '/imports/' + ident + '/process', body, key=key,
                match=read['import_revision']).json()['data'] == accepted.json()['data']
    assert len(calls) == 1 and staff[2].run_one() is None
    current = summary(staff, ident)
    assert current['semantic_calls_used'] == 1 and current['semantic_calls_remaining'] == 0
    if provider == 'outage':
        now = ctx[0][5].get('/api/v1/imports/' + ident).json()['data']
        denied = post(staff, '/imports/' + ident + '/process', {**body, 'mapping_revision': current['mapping_revision']},
                      match=now['import_revision'])
        assert denied.status_code == 409 and denied.json()['error']['code'] == 'LLM_CALL_LIMIT'
    quantity = next(i for i in listing(staff, ident) if i['source_header'] == 'SLX')
    assert quantity['status'] != 'resolved'
    changed = mapping(staff, ident, quantity, {'target_field': 'sales.quantity'})
    assert changed.status_code == 200, changed.text
    no_import_facts(staff)
    prepared = summary(staff, ident)
    assert prepared['completion_guidance']['profiles'][0]['can_submit']
    response, profile, _ = submit(staff, ident)
    assert response.status_code == 201, response.text
    row = response.json()['data']
    owner_session(ctx)
    owner = (staff[0], staff[1], staff[2], ctx[5], staff[4])
    detail = ctx[0][5].get(f'/api/v1/stores/{ctx[2].store_id}/mapping-submissions/{row["submission_id"]}')
    assert detail.status_code == 200, detail.text
    assert detail.json()['data']['spec'] == prepared['profile_proposals'][0]['spec']
    assert any(cell['raw_value'] == ORACLE['first_quantity']
               for cell in detail.json()['data']['evidence']['cells'])
    approved = post(owner, f'/stores/{ctx[2].store_id}/mapping-profiles/{profile["profile_id"]}/decisions',
        dict(decision='approve_activate', proposal_revision=profile['proposal_revision'], expected_active_version=None,
             submission_id=row['submission_id'], expected_submission_version=row['version'], reason='I5 Owner reviewed pinned full spec'),
        match=profile['lifecycle_revision'])
    assert approved.status_code == 200, approved.text
    staff = switch_staff(ctx, staff)
    assert summary(staff, ident)['can_preview']
    no_import_facts(staff)
    preview = previewed(staff, ident)
    sale, = preview['preview']['rows']
    assert sale['after']['quantity'] == ORACLE['expected']['first_total']
    assert sale['after']['unit'] == ORACLE['unit'] and sale['after']['product_id'] == str(staff[4])
    reviewed = confirm(staff, ident, preview)
    assert reviewed.status_code == 200, reviewed.text
    no_import_facts(staff)
    first = finished(staff, ident, commit(staff, ident, preview, reviewed.json()['data']['import_revision']))
    with Session(ctx[0][1]) as fresh:
        persisted = fresh.scalar(select(SalesDaily))
        assert persisted.store_id == ctx[2].store_id and persisted.product_id == staff[4]
        assert persisted.quantity == Decimal(ORACLE['expected']['first_total']) and persisted.is_stockout is None
        assert fresh.get(ImportJob, UUID(accepted.json()['data']['job_id'])).input_json['semantic_attempts'] == 1
    # Same source/profile, new values: no provider or N5; canonical total replaces 100 with 105.
    corrected = analyzed(staff, source(staff[4], ORACLE['corrected_quantity']))
    reused = declare_context(staff, corrected, ORACLE['source_context'])
    assert reused['can_preview'] and reused['profile_proposals'] == [] and len(calls) == 1
    next_preview = previewed(staff, corrected)
    row, = next_preview['preview']['rows']
    assert row['after']['quantity'] == ORACLE['expected']['corrected_total']
    assert row['proposed_action'] == 'REPLACE_DAILY_TOTAL'
    reviewed = confirm(staff, corrected, next_preview)
    assert reviewed.status_code == 200, reviewed.text
    revision = reviewed.json()['data']['import_revision']
    key = str(uuid4())
    replacement = dict(row_id=row['row_id'], action='replace_daily_total', report_business_key=ORACLE['report_key'],
        evidence_reference='I5 explicit same-report correction 100 to 105', reason='Reviewed synthetic correction', disjoint_assertion=False)
    corrected_receipt = finished(staff, corrected, commit(staff, corrected, next_preview, revision,
                                                        key=key, resolutions=[replacement]))
    replay = commit(staff, corrected, next_preview, revision, key=key, resolutions=[replacement])
    assert replay.status_code == 202 and staff[2].run_one() is None
    unchanged = analyzed(staff, source(staff[4], ORACLE['corrected_quantity']))
    declare_context(staff, unchanged, ORACLE['source_context'])
    noop = previewed(staff, unchanged)
    assert noop['preview']['rows'][0]['proposed_action'] == 'NO_OP'
    reviewed = confirm(staff, unchanged, noop)
    noop_receipt = finished(staff, unchanged, commit(staff, unchanged, noop, reviewed.json()['data']['import_revision']))
    assert noop_receipt['outcome'] == 'no_changes' and len(calls) == 1
    with Session(ctx[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(SalesDaily)) == ORACLE['expected']['sale_rows']
        assert fresh.scalar(select(SalesDaily.quantity)) == Decimal(ORACLE['expected']['corrected_total'])
        assert fresh.scalar(select(func.count()).select_from(ImportProfileVersion)) == 1
        audits = fresh.scalars(select(ImportAudit).where(ImportAudit.kind == 'IMPORT_CANONICAL_COMMITTED')).all()
        sources = [s for a in audits for s in a.record_json.get('sales_sources', ())]
        assert sorted(s['source_revision'] for s in sources) == ORACLE['expected']['source_revisions']
        assert {s['product_id'] for s in sources} == {str(staff[4])}
        assert fresh.scalar(select(func.count()).select_from(InventoryMovement)) == 0
    capture = ForecastExecutionUseCases(ctx[0][1]).capture(ForecastExecutionInput(store_id=ctx[2].store_id,
        product_ids=(staff[4],), history_start_date=date(2026, 10, 9), cutoff_date=date(2026, 10, 9)))
    assert len(capture.observations) == 1 and capture.observations[0].quantity == Decimal('105')
    readiness = ctx[0][5].get(f'/api/v1/stores/{ctx[2].store_id}/readiness', params={'actions': 'planning'})
    assert readiness.status_code == 200, readiness.text
    planning = readiness.json()['data']['actions'][0]
    assert not planning['can_execute'] and planning['availability'] != 'ready' and planning['blockers']
    wrong = analyzed(staff, source(staff[4], ORACLE['corrected_quantity']))
    different = declare_context(staff, wrong, {**ORACLE['source_context'], 'source_system_key': 'I5-OTHER-POS'})
    assert not different['binding_refs'] and not different['can_preview'] and len(calls) == 1
    save('synthetic-' + provider, dict(status='PASS', oracle=ORACLE, imports=[ident, corrected, unchanged, wrong],
        provider_calls=len(calls), first_completion=first, correction_completion=corrected_receipt,
        noop_completion=noop_receipt, forecast_capture=capture.model_dump(mode='json'), readiness=readiness.json()['data']))
