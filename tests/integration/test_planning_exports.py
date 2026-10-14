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
    for phrase in ('Nguyên liệu cà phê','Báo cáo phương án','Phụ lục đầy đủ','exact','UNPROVEN',str(run.run_id),run.result_digest):assert phrase in text,phrase
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
    out=Path('runtime/s410');out.mkdir(parents=True,exist_ok=True)
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
