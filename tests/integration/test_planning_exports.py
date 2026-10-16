"""Real ReportLab/Unicode/private bytes and durable PG export behavior."""
from pathlib import Path
from uuid import UUID,uuid4
import hashlib
import pytest
from sqlalchemy.orm import Session
from tests.integration.test_planning_public import flow,config,env,submit,demand_and_offer
from app.application.use_cases.planning_exports import PlanningExports,decode_export
from app.infrastructure.storage.planning_pdf import PlanningPDFStore
from app.infrastructure.planning_pdf_renderer import PlanningPDFRenderer
from app.models import PlanningExport,PlanningRun,Ingredient


@pytest.fixture
def exports(flow,tmp_path):
    c,ingredient,_,worker=flow
    svc=PlanningExports(c[0][5].app.state.planning_public,PlanningPDFStore(tmp_path/'private_pdf'),PlanningPDFRenderer())
    c[0][5].app.state.planning_exports=svc
    return flow,svc


def export(c,location,option=None,key=None,body=None):
    return c[0][5].post(location+'/exports',headers={**c[3],'Idempotency-Key':key or str(uuid4())},
        json=body or dict(format='pdf',option_id=option,locale='vi'))


def test_real_pdf_winner_job_replay_download_and_font_proof(exports):
    flow,svc=exports;c,ingredient,_,worker=flow
    from tests.integration.test_readiness_context import declaration
    from app.application.contracts import import_domains as d
    with Session(c[0][1]) as s:
        s.get(Ingredient,ingredient).name='Nguyên liệu cà phê — đường sữa';s.flush()
        declaration(s,c[1].store_id,d.InventoryDeclaration(kind='INVENTORY',ingredient_id=ingredient,state='CONFIRMED_EMPTY',
            observed_at=c[0][4][0],covered_lot_ids=(),evidence_reference='physical empty after metadata edit'),'inventory')
        s.commit()
    demand_and_offer(flow)
    accepted=submit(c);location=accepted.headers['Location'];run=worker.run_one()
    assert run.status=='completed' and run.outcome=='recommendation_available',[(p.code,p.detail) for p in run.capture.problems]
    key=str(uuid4());response=export(c,location,key=key);assert response.status_code==202,response.text
    receipt=response.json()['data'];download=location+'/exports/'+receipt['export_id'];job='/api/v1/jobs/'+receipt['job_id']
    queued=c[0][5].get(job);assert queued.status_code==200,queued.text
    assert queued.json()['data']['operation']=='planning_pdf_export' and queued.json()['data']['result'] is None
    assert c[0][5].get(download).json()['error']['code']=='EXPORT_NOT_READY'
    record=svc.run_one();assert record.status=='completed',record.error_code
    assert svc.run_one() is None
    polled=c[0][5].get(job);assert polled.status_code==200,polled.text
    result=polled.json()['data']['result'];assert result['resource_type']=='planning_pdf_export'
    pdf=c[0][5].get(download);assert pdf.status_code==200,pdf.text[:400]
    assert pdf.content.startswith(b'%PDF-') and hashlib.sha256(pdf.content).hexdigest()==result['sha256']
    assert pdf.headers['content-type']=='application/pdf' and pdf.headers['cache-control']=='private, no-store'
    assert pdf.headers['etag']=='"'+result['sha256']+'"' and int(pdf.headers['content-length'])==len(pdf.content)==result['byte_count']
    assert pdf.headers['x-content-type-options']=='nosniff'
    assert pdf.headers['content-disposition']==f'attachment; filename="shelfcash-plan-{run.run_id}.pdf"'
    from io import BytesIO
    from pypdf import PdfReader
    reader=PdfReader(BytesIO(pdf.content));assert len(reader.pages)>1
    text='\n'.join(p.extract_text() for p in reader.pages)
    for phrase in ('Nguyên liệu cà phê','Kế hoạch mua hàng','Danh sách mua','Khả năng đáp ứng','CAPTURED_FINITE_DOMAIN_ONLY',str(run.run_id),run.result_digest):assert phrase in ' '.join(text.split()),phrase
    assert 'Phụ lục đầy đủ' not in text and 'daily_balances[' not in text
    assert receipt['render_version']=='planning-pdf/3'
    fonts=[font.get_object() for p in reader.pages for font in p['/Resources']['/Font'].values()]
    assert any('/FontDescriptor' in font and '/FontFile2' in font['/FontDescriptor'].get_object() for font in fonts)
    assert export(c,location,key=key).json()['data']==receipt
    assert export(c,location,option=receipt['option_id'],key=key).status_code==409
    with Session(c[0][1]) as s:
        rows=s.query(PlanningExport).all();assert len(rows)==1 and decode_export(rows[0]).status=='completed'
        assert s.get(PlanningRun,run.run_id).record_digest
        s.get(Ingredient,ingredient).name='Changed after export';s.commit()
    assert c[0][5].get(download).content==pdf.content
    history_path=f'/api/v1/stores/{c[1].store_id}/procurement-plans'
    filters=dict(created_by_user_id=str(c[1].user_id),created_date_from='2026-10-10',created_date_to='2026-10-10')
    before=c[0][5].get(history_path,params=filters).json()['data']
    from app.models.planning_configuration import PlanningBudget
    with Session(c[0][1]) as s:
        cap=s.get(PlanningBudget,c[1].store_id);cap.amount=1;cap.version='c5-explicit-live-cap-change';s.commit()
    assert c[0][5].get(history_path,params=filters).json()['data']==before
    assert before['items'][0]['captured_budget']==dict(availability='available',limit='100',currency='VND')
    from tests.integration.test_discovery_c4 import count_read_queries
    _,discovery=count_read_queries(c[0][1],lambda:c[0][5].get(location+'/exports'))
    found=discovery.json()['data']['items'][0]
    assert found['export_id']==receipt['export_id'] and found['artifact_availability']=='available'
    assert c[0][5].get(found['download_url']).content==pdf.content
    assert found['sha256']==hashlib.sha256(pdf.content).hexdigest()
    # A fresh intent after live name changes renders identical historical facts.
    again=export(c,location);assert again.status_code==202,again.text
    assert svc.run_one().status=='completed'
    assert c[0][5].get(location+'/exports/'+again.json()['data']['export_id']).content==pdf.content
    assert c[0][5].get(location.replace(str(run.run_id),str(uuid4()))+'/exports/'+receipt['export_id']).status_code==404
    out=Path('runtime/p11-pdf/http-pg');out.mkdir(parents=True,exist_ok=True)
    (out/'planning_sample_vi.pdf').write_bytes(pdf.content)
    (out/'n10_actual.json').write_text(response.text,encoding='utf-8')
    (out/'j01_pdf_actual.json').write_text(polled.text,encoding='utf-8')
    (out/'planning_pdf_text.txt').write_text(text,encoding='utf-8')
    # No GET rerender when the private artifact is corrupt.
    artifact=svc.artifacts.root/(receipt['export_id']+'.pdf');artifact.write_bytes(b'%PDF-corrupt')
    assert c[0][5].get(download).json()['error']['code']=='EXPORT_ARTIFACT_UNAVAILABLE'


def test_export_no_winner_explicit_ineligible_and_not_ready_validation(exports):
    flow,svc=exports;c,_,_,worker=flow;demand_and_offer(flow)
    response=submit(c,body=dict(requirements_mode='custom',forecast_start_date='2026-10-10',requirements=dict(
        paths=[dict(path='BASE',min_fill_rate_percent='95',product_overrides=[])],budget_limit='0')))
    location=response.headers['Location']
    assert export(c,location).json()['error']['code']=='RESULT_NOT_READY'
    run=worker.run_one();assert run.status=='completed' and run.outcome=='no_eligible_candidate'
    assert export(c,location).json()['error']['code']=='WINNER_NOT_AVAILABLE'
    read=c[0][5].get(location).json()['data'];option=read['result']['options'][0]
    assert not option['eligible']
    assert export(c,location,option='unknown').json()['error']['code']=='OPTION_NOT_FOUND'
    assert export(c,location,body=dict(format='pdf',locale='vi')).status_code==422
    accepted=export(c,location,option=option['option_id']);assert accepted.status_code==202,accepted.text
    rendered=svc.run_one();assert rendered.status=='completed',rendered.error_code
    result=c[0][5].get(location+'/exports/'+accepted.json()['data']['export_id']);assert result.status_code==200
    from pypdf import PdfReader
    from io import BytesIO
    text='\n'.join(p.extract_text() for p in PdfReader(BytesIO(result.content)).pages)
    assert 'PHƯƠNG ÁN KHÔNG ĐỦ ĐIỀU KIỆN' in text and 'KHÔNG PHẢI KHUYẾN NGHỊ' in text


@pytest.mark.parametrize('old_version', ['planning-pdf/1', 'planning-pdf/2'])
def test_old_version_receipt_replay_retry_and_bytes_survive_upgrade(exports, monkeypatch, old_version):
    """Emulate /1 or /2 acceptance, then execute /3 code against the old job."""
    from app.application.use_cases import planning_exports as module
    from app.application.contracts.planning_export import ExportAccepted
    from app.application.use_cases.planning_exports import document
    from app.repositories.planning import PlanningRepository
    from io import BytesIO
    from pypdf import PdfReader
    flow, svc = exports
    c, _, _, worker = flow
    submitted = submit(c)
    run = worker.run_one()
    assert run.status == 'completed'
    location = submitted.headers['Location']
    key = str(uuid4())
    with monkeypatch.context() as old:
        old.setattr(module, 'ExportAccepted', lambda **fields: ExportAccepted(**fields, render_version=old_version))
        accepted = export(c, location, key=key)
    assert accepted.status_code == 202
    receipt = accepted.json()['data']
    assert receipt['render_version'] == old_version
    # Fresh session reads exactly the retained document used by the old renderer.
    with Session(c[0][1]) as session:
        record, view = svc.public.retained.read(PlanningRepository(session).get(c[1].store_id, run.run_id))
        report = document(record, view, svc._option(view, receipt['option_id']))
    expected = (svc.renderer.render_legacy(report) if old_version == 'planning-pdf/1' else svc.renderer.render_v2(report))
    ident = UUID(receipt['export_id'])
    claimed = svc.claim(ident)
    svc.fail(ident, claimed.claim, 'RENDER_FAILED')
    assert svc.retry_failed(ident).receipt.render_version == old_version
    assert svc.run_one().status == 'completed'
    original = c[0][5].get(location + '/exports/' + receipt['export_id']).content
    assert original == expected
    assert export(c, location, key=key).json()['data'] == receipt
    new = export(c, location).json()['data']
    assert new['render_version'] == 'planning-pdf/3' and new['export_id'] != receipt['export_id']
    assert svc.run_one().status == 'completed'
    current = c[0][5].get(location + '/exports/' + new['export_id']).content
    assert current != original
    original_text = '\n'.join(p.extract_text() for p in PdfReader(BytesIO(original)).pages)
    assert ('Phụ lục đầy đủ' in original_text) == (old_version == 'planning-pdf/1')
    # GET/discovery cannot invoke either template or manufacture another job.
    def forbidden(*args):
        raise AssertionError('Read attempted rendering')
    monkeypatch.setattr(svc.renderer, 'render', forbidden)
    monkeypatch.setattr(svc.renderer, 'render_legacy', forbidden)
    monkeypatch.setattr(svc.renderer, 'render_v2', forbidden)
    assert c[0][5].get(location + '/exports/' + receipt['export_id']).content == original
    items = c[0][5].get(location + '/exports').json()['data']['items']
    assert {item['render_version'] for item in items} == {old_version, 'planning-pdf/3'}
    with Session(c[0][1]) as session:
        rows = session.query(PlanningExport).all()
        assert len(rows) == 2 and all(decode_export(row).status == 'completed' for row in rows)
    # An old artifact/receipt is never a bearer grant after membership revocation.
    from app.models import StoreMembership
    with Session(c[0][1]) as session:
        member = session.query(StoreMembership).filter_by(store_id=c[1].store_id, user_id=c[1].user_id).one()
        member.active = False
        session.commit()
    for retained in (receipt, new):
        denied = c[0][5].get(location + '/exports/' + retained['export_id'])
        assert denied.status_code == 404 and denied.json()['data'] is None
        assert denied.json()['error']['code'] == 'RESOURCE_NOT_FOUND'
    assert export(c, location, key=key).status_code == 404
    assert c[0][5].get(location + '/exports').status_code == 404


def test_unknown_fee_completed_without_option_and_failed_run_cannot_export(exports):
    from datetime import date
    from app.application.contracts import import_domains as d
    from app.application.use_cases.operational_configuration import OperationalConfiguration
    flow, svc = exports
    c, _, _, worker = flow
    with Session(c[0][1]) as session:
        OperationalConfiguration(session, c[1].store_id).fee(d.FeeSource(
            source_fee_key='none', scope='STORE_PROCUREMENT', effective_from=date(2026, 10, 10), effective_to=None,
            mode='PER_OFFER', coverage='UNKNOWN', currency='VND', components=(), covered_source_term_keys=(),
            covered_source_supplier_keys=(), evidence_reference='synthetic unknown fee', reason='explicit fixture'),
            uuid4(), 'synthetic', {}, {})
        session.commit()
    submitted = submit(c)
    run = worker.run_one()
    assert run.status == 'completed' and run.outcome == 'computation_blocked'
    assert export(c, submitted.headers['Location']).json()['error']['code'] == 'WINNER_NOT_AVAILABLE'
    assert export(c, submitted.headers['Location'], option='absent').status_code == 404
    # A durable failed Run is rejected by the existing export gate, not rendered.
    failed = submit(c, body=dict(requirements_mode='custom', forecast_start_date='2026-10-10',
        requirements=dict(paths=[dict(path='BASE', min_fill_rate_percent='95', product_overrides=[])], budget_limit='1')))
    claimed = worker.runs.claim(c[1].store_id, UUID(failed.json()['data']['run_id']))
    worker.runs.fail(c[1].store_id, claimed.run_id, claimed.claim, code='EXECUTION_ERROR')
    assert export(c, failed.headers['Location']).json()['error']['code'] == 'RESULT_NOT_READY'
    with Session(c[0][1]) as session:
        assert session.query(PlanningExport).count() == 0
