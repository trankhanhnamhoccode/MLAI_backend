"""Actual distinct retained candidates and immutable views/PDF after live edits."""
from datetime import date
from uuid import UUID, uuid4
from sqlalchemy.orm import Session
from tests.integration.test_planning_exports import exports, export
from tests.integration.test_planning_public import flow, config, env, submit, demand_and_offer
from app.models import SalesDaily, Ingredient, InventoryLot, Product, SupplierTerm
from app.models.planning_configuration import PlanningBudget
from app.models.model_serving import ModelServingConfiguration


def test_real_alternate_and_all_live_business_changes_leave_history(exports, monkeypatch):
    flow, service = exports
    c, ingredient, _, worker = flow
    client, engine = c[0][5], c[0][1]
    term = demand_and_offer(flow)
    with Session(engine) as s:
        s.add_all([SalesDaily(id=uuid4(),store_id=c[1].store_id,product_id=c[2],
            sales_date=date(2026,10,day),quantity=quantity) for day,quantity in [(7,1),(8,9)]])
        s.commit()
    accepted=submit(c);location=accepted.headers['Location'];run=worker.run_one()
    assert run.status=='completed' and run.outcome=='recommendation_available'
    view=client.get(location).json()['data']
    options=view['result']['options'];winner=view['result']['winner_option_id']
    alternate=next(o for o in options if o['option_id']!=winner and o['eligible'])
    option=alternate['option_id']
    endpoints=[location, location+'/ingredients?option_id='+option,
        location+'/ingredients/'+str(ingredient)+'?option_id='+option,
        location+'/explanation?option_id='+option]
    original=[client.get(p).json()['data'] for p in endpoints]
    detail=original[2]
    assert detail['selected_option_id']==option and detail['selection_status']=='explicit'
    assert detail['purchases']==alternate['purchases'] and len(detail['daily_balances'])==21
    receipt=export(c,location,option=option).json()['data']
    assert service.run_one().status=='completed'
    pdf=client.get(location+'/exports/'+receipt['export_id']).content
    assert pdf.startswith(b'%PDF-')
    with Session(engine) as s:
        s.get(Ingredient,ingredient).name='Changed live label'
        s.get(Product,c[2]).price=999
        s.get(SupplierTerm,term).pack_cost=99
        s.add(InventoryLot(id=uuid4(),store_id=c[1].store_id,ingredient_id=ingredient,
            received_date=date(2026,10,10),expiry_date=None,on_hand_quantity=777,unit='ml',unit_cost=9))
        s.get(PlanningBudget,c[1].store_id).amount='1'
        s.get(ModelServingConfiguration,c[1].store_id).version='changed-live-model-version'
        s.commit()
    from app.infrastructure import import_suggestions
    def forbidden(*args,**kwargs):raise AssertionError('Retained GET attempted provider')
    monkeypatch.setattr(import_suggestions,'suggest_sheet',forbidden)
    monkeypatch.setattr(import_suggestions,'build_opener',forbidden)
    for path,prior in zip(endpoints,original):
        response=client.get(path);assert response.status_code==200,response.text
        assert response.json()['data']==prior
    assert client.get(location).json()['data']['result']['winner_option_id']==winner
    again=export(c,location,option=option);assert again.status_code==202,again.text
    assert service.run_one().status=='completed'
    assert client.get(location+'/exports/'+again.json()['data']['export_id']).content==pdf
    for path in [location+'/exports/not-a-uuid', location+'/ingredients/not-a-uuid']:
        assert client.get(path).status_code==422
    # Raw source/claimed result bindings are verified even for N10 after cache warming.
    from app.models import PlanningRun
    from app.application.planning_serialization import digest
    with Session(engine) as s:
        row=s.get(PlanningRun,run.run_id);raw=dict(row.record_json)
        raw['result_digest']='f'*64;row.record_json=raw;row.record_digest=digest('aggregate',raw);s.commit()
    rejected=export(c,location,option=option)
    assert rejected.status_code==409 and rejected.json()['error']['code']=='RESULT_INTEGRITY_ERROR',rejected.text


def test_explicit_pdf_lifespan_flag_owns_one_real_thread_and_stops(exports):
    from time import perf_counter, sleep
    import threading
    from fastapi.testclient import TestClient
    from app.main import create_app
    flow,service=exports;c,_,_,worker=flow
    demand_and_offer(flow)
    accepted=submit(c);location=accepted.headers['Location'];assert worker.run_one().status=='completed'
    receipt=export(c,location).json()['data']
    assert not c[0][0].pdf_export_worker_enabled
    assert not [t for t in threading.enumerate() if t.name=='shelfcash-pdf-export']
    application=create_app(c[0][0].model_copy(update={'pdf_export_worker_enabled':True}))
    application.state.planning_exports=service
    # The fixture's original app has all workers off. Both ASGI clients stay in
    # this one process; only this explicitly enabled lifespan owns a PDF thread.
    with TestClient(application):
        assert len([t for t in threading.enumerate() if t.name=='shelfcash-pdf-export'])==1
        started=perf_counter()
        while True:
            value=service.job(c[0][5].cookies.get('__Host-shelfcash_session'),UUID(receipt['job_id']))
            if value.status in ('completed','failed'):break
            assert perf_counter()-started<30,'Real local worker did not complete bounded sample'
            sleep(.05)
        assert value.status=='completed',value.error
    assert not [t for t in threading.enumerate() if t.name=='shelfcash-pdf-export']
    response=c[0][5].get(location+'/exports/'+receipt['export_id'])
    assert response.status_code==200 and response.content.startswith(b'%PDF-')


def test_export_rehashed_foreign_store_binding_fails_closed(exports):
    from tests.integration.test_auth_public import setup,login
    from app.models import PlanningExport
    from app.application.planning_serialization import digest
    flow,service=exports;c,_,_,worker=flow
    demand_and_offer(flow)
    accepted=submit(c);location=accepted.headers['Location'];assert worker.run_one().status=='completed'
    receipt=export(c,location).json()['data'];assert service.run_one().status=='completed'
    foreign=setup(c[0],'foreign-integrity@example.test')
    # Labeled DB corruption: recomputed hash and mutually matching export fields
    # must not turn a different Store's retained Run into an authorized artifact.
    with Session(c[0][1]) as s:
        row=s.get(PlanningExport,UUID(receipt['export_id']))
        raw=dict(row.record_json);raw['store_id']=str(foreign.store_id)
        row.store_id=foreign.store_id;row.record_json=raw;row.record_digest=digest('export',raw);s.commit()
    assert login(c[0],'foreign-integrity@example.test').status_code==200
    for path in ['/api/v1/jobs/'+receipt['job_id'],location+'/exports/'+receipt['export_id']]:
        response=c[0][5].get(path)
        assert response.status_code==503 and response.json()['error']['code']=='RESULT_INTEGRITY_UNAVAILABLE',response.text[:300]
