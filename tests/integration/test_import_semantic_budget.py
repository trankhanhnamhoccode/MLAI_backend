"""I3 explicit priority and durable accounting on the owned PostgreSQL database."""
import io
from concurrent.futures import ThreadPoolExecutor
from urllib.error import URLError
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.use_cases.import_staging import ImportStaging
from app.infrastructure import import_suggestions as gateway
from app.models.import_staging import ImportBatch, ImportJob
from tests.integration.test_auth_public import env
from tests.integration.test_import_staging import post, sales_bytes, approved, previewed
from tests.integration.test_import_rule_review import summary, declare_context
from tests.integration.test_import_qwen_review import upload
from tests.integration.test_import_classification import listing, mapping
from tests.integration.import_semantic_helpers import request_semantics, semantic_imp as imp, base_imp


def job_view(imp, accepted):
    return imp[0][5].get('/api/v1/jobs/' + accepted['job_id']).json()['data']


def multi(imp, count):
    ident = post(imp, f'/stores/{imp[1].store_id}/imports',
                 {'data_date': '2026-10-09'}).json()['data']['import_id']
    content = sales_bytes(imp).replace(b'sales.quantity', b'alien')
    response = imp[0][5].post('/api/v1/imports/' + ident + '/files',
        files=[('files[]', (f'priority-{n}.csv', content.replace(b'REPORT-1', f'R-{n}'.encode()),
                           'text/csv')) for n in range(count)],
        data={'client_file_ids[]': [str(uuid4()) for _ in range(count)]},
        headers={**imp[3], 'Idempotency-Key': str(uuid4())})
    assert response.status_code == 200, response.text
    data = response.json()['data']
    response = post(imp, '/imports/' + ident + '/analyze', dict(
        file_set_version=data['file_set_version'], accepted_file_ids=[f['file_id'] for f in data['items']],
        acknowledged_rejected_client_file_ids=[]), match=data['import_revision'])
    assert response.status_code == 202, response.text
    imp[2].run_one()
    return ident


@pytest.mark.parametrize('limit', [0, 1, 10])
def test_capture_at_acceptance_and_live_configuration_cannot_change_limit(imp, monkeypatch, limit):
    imp[2].settings = imp[2].settings.model_copy(update={'import_semantic_sheet_limit': limit})
    ident, _, _, _, _ = upload(imp, sales_bytes(imp).replace(b'sales.quantity', b'alien'))
    imp[2].settings = imp[2].settings.model_copy(update={'import_semantic_sheet_limit': 2})
    imp[2].run_one()
    current = declare_context(imp, ident)
    assert current['semantic_call_limit'] == current['semantic_calls_remaining'] == limit
    assert current['semantic_configured_limit'] == 2
    with Session(imp[0][1]) as fresh:
        batch = fresh.get(ImportBatch, UUID(ident))
        analyze = fresh.scalar(select(ImportJob).where(ImportJob.import_id == batch.id,
                                                     ImportJob.operation == 'import_analyze'))
        assert batch.analysis_json['semantic_budget'] == analyze.input_json['semantic_budget']
        assert batch.analysis_json['semantic_budget']['limit'] == limit
    calls = []
    monkeypatch.setattr(gateway, 'suggest_sheet', lambda *a: (calls.append(1) or (None, 'LLM_UNAVAILABLE')))
    if limit:
        request_semantics(imp, ident, declare=False)
        assert len(calls) == 1
        assert summary(imp, ident)['semantic_calls_remaining'] == limit - 1
    else:
        read = imp[0][5].get('/api/v1/imports/' + ident).json()['data']
        response = post(imp, '/imports/' + ident + '/process', dict(phase='semantic_suggestions',
            mapping_revision=current['mapping_revision'], sheet_ids=[current['sheets'][0]['sheet_id']]),
            match=read['import_revision'])
        assert response.status_code == 409 and response.json()['error']['code'] == 'LLM_CALL_LIMIT'
        assert not calls and summary(imp, ident)['semantic_calls_used'] == 0
        alien = next(i for i in listing(imp, ident) if i['source_header'] == 'alien')
        assert mapping(imp, ident, alien, {'target_field': 'sales.quantity'}).status_code == 200
        approved(imp, ident)
        assert previewed(imp, ident)['preview']['rows'][0]['after']['quantity'] == '105'
        assert not calls


def test_retained_analysis_keeps_two_even_when_operator_config_is_zero(imp):
    ident = multi(imp, 1)
    with Session(imp[0][1]) as s:
        batch = s.get(ImportBatch, UUID(ident))
        data = dict(batch.analysis_json)
        data.pop('semantic_budget')
        batch.analysis_json = data
        s.commit()
    imp[2].settings = imp[2].settings.model_copy(update={'import_semantic_sheet_limit': 0})
    assert summary(imp, ident)['semantic_call_limit'] == 2
    assert summary(imp, ident)['semantic_configured_limit'] == 0


@pytest.mark.parametrize('limit,order', [(1, [2, 0, 1]), (2, [1, 2, 0]), (2, [0, 2, 1]), (10, list(range(10, -1, -1)))])
def test_request_order_allocates_without_silent_truncation(imp, monkeypatch, limit, order):
    imp[2].settings = imp[2].settings.model_copy(update={'import_semantic_sheet_limit': limit})
    ident = multi(imp, len(order))
    sheets = summary(imp, ident)['sheets']
    ids = [sheets[n]['sheet_id'] for n in order]
    calls = []
    monkeypatch.setattr(gateway, 'suggest_sheet', lambda *a: (calls.append(str(a[1].sheet_id)) or (None, 'LLM_UNAVAILABLE')))
    accepted = request_semantics(imp, ident, ids, run=False)
    queued = job_view(imp, accepted)['semantic_allocation']
    assert [a['sheet_id'] for a in queued] == ids
    assert all(a['status'] == 'scheduled' and not a['slot_consumed'] for a in queued)
    imp[2].run_one()
    result = job_view(imp, accepted)
    assert calls == ids[:limit]
    assert [o['sheet_id'] for o in result['result']['outcomes']] == ids
    assert [o['requested_position'] for o in result['result']['outcomes']] == list(range(1, len(ids) + 1))
    assert [o['slot_consumed'] for o in result['result']['outcomes']] == [n < limit for n in range(len(ids))]
    assert [o['status'] for o in result['result']['outcomes']] == ['unavailable'] * limit + ['call_limit'] * (len(ids) - limit)
    assert result['semantic_allocation'] == result['result']['outcomes']
    with Session(imp[0][1]) as fresh:
        assert fresh.get(ImportJob, UUID(accepted['job_id'])).input_json['semantic_attempts'] == limit


@pytest.mark.parametrize('failure', ['disabled', 'missing', 'blank', 'input'])
def test_known_preflight_failures_do_not_reserve_or_dispatch(imp, monkeypatch, failure):
    from pydantic import SecretStr
    content = sales_bytes(imp).replace(b'sales.quantity', b'alien')
    if failure == 'input':
        # Header count stays valid; long untrusted filenames in related context are
        # not needed: bounded rows/columns with escaped lexical values exceed bytes.
        content = (','.join(['sales.product_id', 'sales.sales_date', 'alien', 'sales.unit',
                            'sales.business_report_key'] + [f'unknown{n}' for n in range(27)]) + '\n' +
                   '\n'.join(','.join([str(imp[4]), '2026-10-09', '0', 'cup', f'R{r}'] +
                                     ['\x01' * 200] * 27) for r in range(8)) + '\n').encode()
    ident, _, _, _, _ = upload(imp, content)
    imp[2].run_one()
    if failure == 'disabled':
        imp[2].settings = imp[2].settings.model_copy(update={'import_llm_suggestions_enabled': False})
    elif failure in {'missing', 'blank'}:
        imp[2].settings = imp[2].settings.model_copy(update={'openrouter_api_key': None if failure == 'missing' else SecretStr('   ')})
    monkeypatch.setattr(gateway, 'suggest_sheet', lambda *a: pytest.fail('known preflight failure must not dispatch'))
    accepted = request_semantics(imp, ident)
    outcome = job_view(imp, accepted)['result']['outcomes'][0]
    assert outcome['status'] == 'unavailable' and not outcome['slot_consumed']
    assert outcome['diagnostic']['attempts'] == 0
    assert outcome['diagnostic']['failure_stage'] == ('input' if failure == 'input' else 'configuration')
    assert summary(imp, ident)['semantic_calls_used'] == 0
    with Session(imp[0][1]) as fresh:
        assert fresh.get(ImportJob, UUID(accepted['job_id'])).input_json['semantic_attempts'] == 0


def test_transport_retries_are_one_slot_and_two_workers_do_not_duplicate(imp, monkeypatch):
    ident = multi(imp, 1)
    calls = []
    class Transport:
        def open(self, request, timeout):
            calls.append(1)
            if len(calls) == 1:
                raise URLError('synthetic outage')
            return io.BytesIO(b'{}')
    monkeypatch.setattr(gateway, 'build_opener', lambda *a: Transport())
    accepted = request_semantics(imp, ident, run=False)
    other = ImportStaging(imp[0][2], imp[2].settings)
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda worker: worker.run_one(), [imp[2], other]))
    assert results.count(UUID(accepted['job_id'])) == 1 and len(calls) == 2
    outcome = job_view(imp, accepted)['result']['outcomes'][0]
    assert outcome['slot_consumed'] and outcome['diagnostic']['attempts'] == 2
    assert summary(imp, ident)['semantic_calls_used'] == 1


def test_preflight_skip_leaves_slot_for_next_requested_sheet_and_never_calls_outside_subset(imp, monkeypatch):
    from app.application.contracts.import_mapping import SuggestionDiagnostic
    imp[2].settings = imp[2].settings.model_copy(update={'import_semantic_sheet_limit': 1})
    ident = multi(imp, 3)
    ids = [s['sheet_id'] for s in summary(imp, ident)['sheets']]
    requested = [ids[2], ids[0]]
    prepare = gateway.prepare_sheet
    def preflight(settings, sheet, *args):
        if str(sheet.sheet_id) == requested[0]:
            return None, SuggestionDiagnostic(status='unavailable', model=settings.openrouter_mapping_model,
                failure_code='LLM_INPUT_LIMIT', failure_stage='input')
        return prepare(settings, sheet, *args)
    monkeypatch.setattr(gateway, 'prepare_sheet', preflight)
    calls = []
    monkeypatch.setattr(gateway, 'suggest_sheet', lambda *a: (calls.append(str(a[1].sheet_id)) or (None, 'LLM_UNAVAILABLE')))
    accepted = request_semantics(imp, ident, requested)
    outcomes = job_view(imp, accepted)['result']['outcomes']
    assert calls == [requested[1]]
    assert [o['slot_consumed'] for o in outcomes] == [False, True]
    assert ids[1] not in [o['sheet_id'] for o in outcomes]
    assert summary(imp, ident)['semantic_calls_used'] == 1


def test_crash_after_reservation_is_retained_and_never_blindly_retried(imp, monkeypatch):
    import app.application.use_cases.import_staging as module
    ident = multi(imp, 1)
    accepted = request_semantics(imp, ident, run=False)
    def crash(*args):
        raise SystemExit('synthetic process death after durable reserve')
    monkeypatch.setattr(gateway, 'suggest_sheet', crash)
    with pytest.raises(SystemExit):
        imp[2].run_one()
    interrupted = job_view(imp, accepted)
    assert interrupted['semantic_allocation'][0]['status'] == 'attempted'
    assert interrupted['semantic_allocation'][0]['slot_consumed']
    restarted = ImportStaging(imp[0][2], imp[2].settings)
    monkeypatch.setattr(module, 'liveness', lambda *a: 'DEAD')
    assert restarted.recover() == (UUID(accepted['job_id']),)
    assert restarted.run_one() is None
    assert job_view(imp, accepted)['error']['code'] == 'IMPORT_EXECUTOR_INTERRUPTED'
    assert summary(imp, ident)['semantic_calls_remaining'] == 1
    monkeypatch.setattr(gateway, 'suggest_sheet', lambda *a: (None, 'LLM_UNAVAILABLE'))
    request_semantics(imp, ident, declare=False)
    assert summary(imp, ident)['semantic_calls_used'] == 2
