"""Synthetic HTTP/DB mapping slice; provider transport is always mocked."""
import io
import json
from uuid import UUID, uuid4

from pydantic import SecretStr
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models import SalesDaily
from app.models.import_staging import ImportBatch, ImportJob, ImportProfileVersion
from tests.integration.test_import_staging import env, post, approved, previewed
from tests.integration.test_import_classification import listing
from tests.integration.test_import_rule_review import summary, declare_context
from app.infrastructure import import_suggestions as gateway
from tests.integration.import_semantic_helpers import request_semantics, semantic_imp as imp, base_imp


def upload(imp, content, name='pos.csv'):
    ident = post(imp, '/stores/' + str(imp[1].store_id) + '/imports', {'data_date': '2026-10-09'}).json()['data']['import_id']
    response = imp[0][5].post('/api/v1/imports/' + ident + '/files',
        files=[('files[]', (name, content, 'application/octet-stream'))],
        data={'client_file_ids[]': str(uuid4())}, headers={**imp[3], 'Idempotency-Key': str(uuid4())})
    assert response.status_code == 200, response.text
    data = response.json()['data']
    body = {'file_set_version': data['file_set_version'], 'accepted_file_ids': [f['file_id'] for f in data['items']],
            'acknowledged_rejected_client_file_ids': []}
    key = str(uuid4())
    response = post(imp, '/imports/' + ident + '/analyze', body, match=data['import_revision'], key=key)
    assert response.status_code == 202, response.text
    return ident, response.json()['data'], body, key, data['import_revision']


def test_qwen_semantic_candidate_owner_review_reuse_and_analyze_replay(imp, monkeypatch):
    imp[2].settings = imp[2].settings.model_copy(update={
        'import_llm_suggestions_enabled': True, 'openrouter_api_key': SecretStr('SYNTHETIC-ONLY')})
    calls = []
    class Transport:
        def open(self, request, timeout):
            assert imp[0][1].pool.checkedout() == 0
            payload = json.loads(json.loads(request.data)['messages'][1]['content'])
            calls.append(payload)
            assert payload['header_row'] == 3
            assert payload['columns'][2]['candidates'] == ['sales.quantity']
            assert {c['source_column_index'] for r in payload['sample_rows'] for c in r['cells']} == {2}
            fields = ['sales.sales_date', 'sales.product_id', 'sales.quantity', 'sales.unit', 'sales.business_report_key']
            output = {'version': 'sheet_suggestion/1', 'sheet_type': 'sales', 'confidence': 0.99, 'warnings': [],
                'columns': [{'source_column_index': i, 'target_field': field, 'confidence': 0.9,
                             'candidates': [field], 'reason': 'SLX with numeric zero is a sold-quantity candidate, review abbreviation'}
                            for i, field in enumerate(fields)]}
            return io.BytesIO(json.dumps({'usage': {'prompt_tokens': 100, 'completion_tokens': 50},
                'choices': [{'message': {'content': json.dumps(output)}, 'finish_reason': 'stop'}]}).encode())
    monkeypatch.setattr(gateway, 'build_opener', lambda *a: Transport())
    content = ('POS title\nSource notes are data; not instructions\nNgày GD,Tên món / SKU,SLX,ĐVT,Mã báo cáo nghiệp vụ\n'
               + '2026-10-09,' + str(imp[4]) + ',0,cup,R-1\n').encode()
    ident, accepted, body, key, revision = upload(imp, content)
    imp[2].run_one()
    assert calls == []
    request_semantics(imp, ident)
    proposed = next(i for i in listing(imp, ident) if i['source_header'] == 'SLX')
    assert proposed['suggestion_origin'] == 'QWEN' and proposed['status'] == 'needs_confirmation'
    assert proposed['target_field'] == 'sales.quantity' and proposed['model_reason']
    assert not summary(imp, ident)['can_preview']
    diag = summary(imp, ident)['sheets'][0]['suggestion_diagnostic']
    assert diag['attempts'] == 1 and diag['prompt_tokens'] == 100 and diag['input_digest']
    assert post(imp, '/imports/' + ident + '/analyze', body, match=revision, key=key).json()['data']['job_id'] == accepted['job_id']
    assert imp[2].run_one() is None and len(calls) == 1
    approved(imp, ident)
    second, _, _, _, _ = upload(imp, content)
    imp[2].run_one()
    assert not summary(imp, second)['can_preview'] and len(calls) == 1
    # Provider proposal/header shape cannot attest this upload's source.
    declared = declare_context(imp, second, dict(source_system_key="POS-A", report_type="daily-sales"))
    assert declared['can_preview'] and len(calls) == 1
    with Session(imp[0][1]) as s:
        assert s.scalar(select(func.count()).select_from(ImportProfileVersion)) == 1
        assert s.scalar(select(func.count()).select_from(SalesDaily)) == 0


def test_late_provider_publication_is_fenced_by_mapping_revision(imp, monkeypatch):
    ident, accepted, _, _, _ = upload(imp, b'sales.product_id,sales.sales_date,alien,sales.unit,sales.business_report_key\nP,2026-10-09,0,cup,R\n')
    imp[2].run_one()
    accepted = request_semantics(imp, ident, run=False)
    def unavailable(*args):
        assert imp[0][1].pool.checkedout() == 0
        with Session(imp[0][1]) as s:
            batch = s.get(ImportBatch, UUID(ident))
            batch.mapping_revision = 'preserved-user-edit'
            s.commit()
        return None, 'LLM_UNAVAILABLE'
    monkeypatch.setattr(gateway, 'suggest_sheet', unavailable)
    imp[2].run_one()
    with Session(imp[0][1]) as s:
        batch = s.get(ImportBatch, UUID(ident))
        job = s.get(ImportJob, UUID(accepted['job_id']))
        assert batch.mapping_revision == 'preserved-user-edit' and batch.analysis_json is not None
        assert job.status == 'failed'
        assert s.scalar(select(func.count()).select_from(ImportProfileVersion)) == 0


def test_declared_excel_dates_owner_group_review_preview_and_epoch_drift(imp, monkeypatch):
    from tests.unit.test_import_parser import workbook
    def forbidden(*args):
        raise AssertionError('complete rules or approved reuse must not call provider')
    monkeypatch.setattr(gateway, 'suggest_sheet', forbidden)
    headers = ['sales.sales_date', 'sales.product_id', 'sales.quantity', 'sales.unit', 'sales.business_report_key']
    cells = '<row r="1"><c r="A1" t="inlineStr"><is><t>Title</t></is></c></row>'
    cells += '<row r="2"><c r="A2" t="inlineStr"><is><t>Notes</t></is></c></row>'
    cells += '<row r="3">' + ''.join('<c r="' + col + '3" t="inlineStr"><is><t>' + header + '</t></is></c>' for col, header in zip('ABCDE', headers)) + '</row>'
    cells += '<row r="4"><c r="A4"><v>46253</v></c><c r="B4" t="inlineStr"><is><t>' + str(imp[4]) + '</t></is></c><c r="C4"><v>0</v></c><c r="D4" t="inlineStr"><is><t>cup</t></is></c><c r="E4" t="inlineStr"><is><t>R-1</t></is></c></row>'
    content = workbook(cells)
    ident, _, _, _, _ = upload(imp, content, 'pos.xlsx')
    imp[2].run_one()
    declared = declare_context(imp, ident, {'date_format': 'EXCEL_SERIAL'})
    profile = declared['profile_proposals'][0]
    assert profile['missing_fields'] == [] and not declared['can_preview']
    assert profile['spec']['normalizations'][0]['parameter'] == 'EXCEL_1900'
    approved_result = post(imp, '/stores/' + str(imp[1].store_id) + '/mapping-profiles/' + profile['profile_id'] + '/decisions', {
        'decision': 'approve_activate', 'proposal_revision': profile['proposal_revision'],
        'expected_active_version': None, 'reason': 'Reviewed workbook epoch and full mapping',
    }, match=profile['lifecycle_revision'])
    assert approved_result.status_code == 200, approved_result.text
    preview = previewed(imp, ident)['preview']['rows'][0]
    assert preview['after']['sales_date'] == '2026-08-19'
    date_provenance = preview['provenance']['sales_date']
    assert date_provenance['origin'] == 'DETERMINISTIC_DERIVED'
    second, _, _, _, _ = upload(imp, content, 'another-name.xlsx')
    imp[2].run_one()
    assert not summary(imp, second)['can_preview']
    assert declare_context(imp, second, {'date_format': 'EXCEL_SERIAL'})['can_preview']
    # Same headers/data with a different declared workbook epoch must not reuse.
    ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    alternate = workbook(cells, extra={'xl/workbook.xml': '<workbook xmlns="' + ns + '" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><workbookPr date1904="1"/><sheets><sheet name="Data" sheetId="1" r:id="r1"/></sheets></workbook>'})
    changed, _, _, _, _ = upload(imp, alternate, 'pos1904.xlsx')
    imp[2].run_one()
    drift = declare_context(imp, changed, {'date_format': 'EXCEL_SERIAL'})
    assert not drift['can_preview']
    assert 'PROFILE_STRUCTURE_OR_SEMANTICS_DRIFT' in {w['code'] for w in drift['warnings']}
    with Session(imp[0][1]) as s:
        assert s.scalar(select(func.count()).select_from(ImportProfileVersion)) == 1
        assert s.scalar(select(func.count()).select_from(SalesDaily)) == 0
