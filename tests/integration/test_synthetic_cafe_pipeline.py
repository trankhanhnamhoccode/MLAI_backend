"""Fictional workbooks through public Import/worker and real forecast/BOM/MILP/selector."""
import json
import hashlib
import os
from datetime import date,datetime,timedelta
from fractions import Fraction
from pathlib import Path
from uuid import UUID,uuid4

import pytest
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from app.application.use_cases.import_staging import ImportStaging
from app.models import Product,Ingredient,Supplier,InventoryLot,InventoryMovement,Recipe,SalesDaily,PlanningRun
from app.models.operational_import import InventoryReceiptRecord
from app.models.import_history import ImportHistoryRecord
from tests.integration.test_auth_public import env,setup,login,ORIGIN
from tests.integration.test_import_setup_stock import complete
from tests.integration.test_import_classification import mapping
from tests.integration.test_import_rule_review import summary
from tests.integration.import_i5_evidence import save,i5_trace

FIXTURE=Path(__file__).parents[1]/'fixtures/synthetic_cafe_v1'
DATA=json.loads((FIXTURE/'dataset.json').read_text(encoding='utf-8'))
CUTOFF=date.fromisoformat(DATA['manifest']['cutoff'])
HISTORY_START=date.fromisoformat(DATA['manifest']['history_start'])


@pytest.fixture
def cafe(env):
    env[4][0]=datetime.fromisoformat(DATA['manifest']['cutoff_timestamp'])
    receipt=setup(env);wire=login(env).json()['data']
    service=ImportStaging(env[2],env[0].model_copy(update={'import_llm_suggestions_enabled':False}))
    env[5].app.state.import_staging=service
    return env,receipt,service,{'Origin':ORIGIN,'X-CSRF-Token':wire['session']['csrf_token']},None


def exact(value):return Fraction(int(value['numerator']),int(value['denominator']))


def upload(c,path):
    from tests.integration.test_import_staging import post
    ident=post(c,'/stores/'+str(c[1].store_id)+'/imports',{'data_date':str(CUTOFF)}).json()['data']['import_id']
    response=c[0][5].post('/api/v1/imports/'+ident+'/files',headers={**c[3],'Idempotency-Key':str(uuid4())},
        files=[('files[]',(path.name,path.read_bytes(),'application/octet-stream'))],data={'client_file_ids[]':str(uuid4())})
    assert response.status_code==200,response.text
    data=response.json()['data']
    response=post(c,'/imports/'+ident+'/analyze',dict(file_set_version=data['file_set_version'],
        accepted_file_ids=[r['file_id'] for r in data['items']],acknowledged_rejected_client_file_ids=[]),match=data['import_revision'])
    assert response.status_code==202,response.text
    assert c[2].run_one()==UUID(response.json()['data']['job_id'])
    return ident


def select_scope(c,ident,scope_only):
    items=[];cursor=None
    while True:
        params={'review_only':'false','limit':100}
        if cursor:params['cursor']=cursor
        wire=c[0][5].get('/api/v1/imports/'+ident+'/mappings',params=params).json()
        items.extend(wire['data']['items']);cursor=wire['meta']['pagination']['next_cursor']
        if not cursor:break
    for sheet in summary(c,ident)['sheets']:
        ignore=sheet['name']=='SYNTHETIC_README' or ((sheet['name']=='scope_declarations') != scope_only)
        if not ignore:continue
        issue=next(i for i in items if i['sheet_id']==sheet['sheet_id'] and i['issue_type']=='classification')
        response=mapping(c,ident,issue,{'resolution':dict(kind='sheet_type',sheet_type=None,ignored=True,acknowledgment=True,
            reason='Explicit synthetic two-stage scope; raw retained, declarations follow canonical lot creation; external week never uploaded')})
        assert response.status_code==200,response.text


def review_fixture(c,ident,context,creations=None,bindings=None):
    """Owner reviews eligible exact canonical columns in full spec, current policy."""
    from tests.integration.test_import_staging import post
    creations=dict(creations or {});bindings=bindings or {};attempted=set()
    for _ in range(100):
        items=[];cursor=None
        while True:
            params={'review_only':'false','limit':100}
            if cursor:params['cursor']=cursor
            wire=c[0][5].get('/api/v1/imports/'+ident+'/mappings',params=params).json()
            items.extend(wire['data']['items']);cursor=wire['meta']['pagination']['next_cursor']
            if not cursor:break
        pending=[i for i in items if i['status'] not in {'resolved','auto_mapped'} and not i['ignored']
            and not (i['issue_type']=='column' and i['suggestion_origin']=='RULE'
                and i['target_field'] and i['candidate_targets']==[i['target_field']])]
        if not pending:break
        item=min(pending,key=lambda i:{'classification':0,'source_context':1,'identity':2}.get(i['issue_type'],3))
        assert item['mapping_id'] not in attempted,item
        attempted.add(item['mapping_id'])
        if item['issue_type']=='classification':
            sheet=next(s for s in summary(c,ident)['sheets'] if s['sheet_id']==item['sheet_id'])
            resolution=dict(kind='sheet_type',sheet_type=sheet['selected_type'],reason='Explicit synthetic supported schema')
        elif item['issue_type']=='source_context':
            resolution=dict(kind='source_context',evidence_reference=DATA['manifest']['origin'],**context)
        elif item['issue_type']=='identity':
            token=item['source_header']
            if token in creations:
                entity,metadata=creations.pop(token)
                resolution=dict(kind='new_entity_proposal',entity=entity,source_business_key=token,metadata=metadata,
                    evidence_reference=DATA['manifest']['origin'])
            else:
                reserved={e['source_business_key']:e['reserved_canonical_id'] for p in summary(c,ident)['profile_proposals']
                    for e in (p.get('spec') or {}).get('entity_proposals',())}
                resolution=dict(kind='identity_binding',canonical_id=str(bindings.get(token) or reserved[token]))
        else:raise AssertionError(item)
        response=mapping(c,ident,item,{'resolution':resolution});assert response.status_code==200,response.text
    else:raise AssertionError('Synthetic manual review did not finish')
    for proposal in summary(c,ident)['profile_proposals']:
        assert not proposal['missing_fields'],proposal
        response=post(c,f"/stores/{c[1].store_id}/mapping-profiles/{proposal['profile_id']}/decisions",dict(
            decision='approve_activate',proposal_revision=proposal['proposal_revision'],expected_active_version=proposal['active_version'],
            reason='Owner reviews complete exact canonical spec and explicit synthetic declarations'),match=proposal['lifecycle_revision'])
        assert response.status_code==200,response.text


def import_scenario(c,case):
    config=DATA['manifest']['scenarios'][case];path=FIXTURE/config['file'];sheets=DATA['workbooks'][config['file']]
    ident=upload(c,path);select_scope(c,ident,False)
    creations={r['name']:('product',{k:v for k,v in r.items() if k!='source_business_key'}) for r in sheets['products']}
    for _,metadata in creations.values():metadata['price']=str(metadata['price'])
    creations.update({r['name']:('ingredient',{k:v for k,v in r.items() if k!='source_business_key'}) for r in sheets['ingredients']})
    creations.update({r['name']:('supplier',{k:v for k,v in r.items() if k!='source_supplier_key'}) for r in sheets['suppliers']})
    context=dict(source_system_key=DATA['manifest']['source_system_key'],report_type='CAFE_INPUT_V1',
        date_format='EXCEL_SERIAL',sales_semantics='daily_total')
    review_fixture(c,ident,context,creations=creations)
    with Session(c[0][1]) as fresh:
        for model in (Product,Ingredient,Supplier,Recipe,SalesDaily,InventoryLot,InventoryMovement):
            assert fresh.scalar(select(func.count()).select_from(model))==0
    read,done=complete(c,ident)
    assert done['outcome']=='committed'
    with Session(c[0][1]) as fresh:
        products={r.name:r.id for r in fresh.scalars(select(Product))}
        ingredients={r.name:r.id for r in fresh.scalars(select(Ingredient))}
        suppliers={r.name:r.id for r in fresh.scalars(select(Supplier))}
        lots={r.lot_code:r.id for r in fresh.scalars(select(InventoryLot))}
        assert len(products)==4 and len(ingredients)==5 and len(suppliers)==1 and len(lots)==len(sheets['opening_stock'])
        assert fresh.scalar(select(func.count()).select_from(SalesDaily))==728
        assert fresh.scalar(select(func.count()).select_from(InventoryMovement))==len(lots)
        assert fresh.scalar(select(func.count()).select_from(InventoryReceiptRecord))==len(lots)
        for domain in ('usage_history','purchase_history'):
            assert fresh.scalar(select(func.count()).select_from(ImportHistoryRecord).where(ImportHistoryRecord.domain==domain))==len(sheets[domain])
        for row in sheets['products']:
            product=fresh.get(Product,products[row['name']])
            assert product.sku==row['sku'] and product.selling_unit==row['selling_unit'] and product.price==row['price']
        for row in sheets['ingredients']:
            ingredient=fresh.get(Ingredient,ingredients[row['name']])
            assert ingredient.sku==row['sku'] and ingredient.base_unit==row['base_unit'] and ingredient.expiry_tracking is row['expiry_tracking']
        assert fresh.scalar(select(func.max(SalesDaily.sales_date)))==CUTOFF
        for row in sheets['opening_stock']:
            lot=fresh.get(InventoryLot,lots[row['lot_code']])
            assert lot.ingredient_id==ingredients[row['ingredient_id']] and lot.supplier_id==suppliers[row['supplier_id']]
            assert lot.on_hand_quantity==row['quantity'] and lot.unit_cost==row['unit_cost']
            assert str(lot.received_date)==row['received_date']
            assert (str(lot.expiry_date) if lot.expiry_date else None)==row['expiry_date']
    second=upload(c,path);select_scope(c,second,True)
    review_fixture(c,second,context,bindings=products|ingredients|suppliers|lots)
    complete(c,second)
    return config,products,ingredients,lots,ident


@pytest.mark.parametrize('case',['main','sufficient','insufficient_budget'])
def test_synthetic_workbooks_public_pipeline_and_sealed_external_week(cafe,case,monkeypatch,i5_trace):
    verify_pipeline(cafe,case,monkeypatch,i5_trace)


def verify_pipeline(cafe,case,monkeypatch,i5_trace,*,train_candidate=True):
    from app.infrastructure import import_suggestions
    monkeypatch.setattr(import_suggestions,'suggest_sheet',lambda *a,**kw:pytest.fail('real provider forbidden'))
    c=cafe;config,products,ingredients,lots,ident=import_scenario(c,case)
    from app.application.use_cases.readiness import ReadinessReads
    from app.application.use_cases.planning_public import PublicPlanning
    from app.application.use_cases.planning_configuration import PlanningConfigurationWrites
    from app.application.use_cases.planning_worker import PlanningExecution
    from tests.integration.test_readiness_context import configure_baseline
    configure_baseline(c)
    client=c[0][5];base=f'/api/v1/stores/{c[1].store_id}'
    client.app.state.readiness=ReadinessReads(c[0][2],client.app.state.forecast_serving,planning_available=lambda:True)
    client.app.state.planning_configuration=PlanningConfigurationWrites(c[0][2])
    client.app.state.planning_public=PublicPlanning(c[0][2],client.app.state.forecast_serving)
    budget=client.put(base+'/planning-budget',headers={**c[3],'Idempotency-Key':str(uuid4()),'If-None-Match':'*'},json={'amount':config['budget']})
    assert budget.status_code==201,budget.text
    c[0][4][0]+=timedelta(seconds=2)  # Import/stock captured at D; run accepted just after midnight D+1.
    start=CUTOFF+timedelta(days=1)
    preparation=client.app.state.forecast_serving.prepare(c[1].store_id,start)
    prepared=preparation.prepared
    assert len(prepared.observations)==728 and max(o.sales_date for o in prepared.observations)==CUTOFF
    assert prepared.request.history_start_date==HISTORY_START
    assert len(prepared.forecast_dates)==7 and min(prepared.forecast_dates)==start
    from app.infrastructure.forecast_model import training_rows
    rows=training_rows(prepared)
    assert all(r.status=='READY' and r.observation_count==182 for r in rows.readiness)
    # The current supported serving operator is BASELINE. Candidate training is
    # independently real and causal, not an unsupported activation via ORM seed.
    report=None;candidate_forecast=None;artifact_identity=None
    if case=='main' and train_candidate:
        from app.application.use_cases.forecast_evaluation import backtest
        report=backtest(prepared,'SYNTHETIC')
        assert list(map(str,report.validation_origins))==DATA['manifest']['validation_origins']
        assert list(map(str,report.holdout_origins))==DATA['manifest']['internal_holdout_origins']
        assert not report.excluded and report.missing_targets==0
        from app.infrastructure.forecast_model import train_quantiles,predict_quantiles
        from app.infrastructure.storage.forecast_artifacts import ForecastArtifactStore
        artifacts=ForecastArtifactStore(Path(os.environ.get('I5_EVIDENCE_DIRECTORY','runtime/verification/synthetic-cafe/evidence')).parent/'model_artifacts')
        artifact_identity=artifacts.publish(train_quantiles(prepared),report)
        loaded=artifacts.load(artifact_identity)
        assert loaded.model.prepared.request.cutoff_date==CUTOFF
        candidate_forecast,_,_=predict_quantiles(loaded.model,prepared,artifact_identity)
    accepted=client.post(base+'/procurement-plans',headers={**c[3],'Idempotency-Key':str(uuid4())},json=dict(
        requirements_mode='custom',forecast_start_date=str(start),requirements=dict(paths=[dict(path='BASE',
        min_fill_rate_percent='100',product_overrides=[])],budget_limit=None)))
    assert accepted.status_code==202,accepted.text
    record=PlanningExecution(c[0][2],client.app.state.forecast_serving).run_one()
    assert record.status=='completed',(record.error_code,record.capture.problems)
    source=DATA['workbooks'][config['file']]
    # Independent recipe multiplication from retained forecast, for every path/day.
    assert record.result.bom.status=='COMPLETE'
    expected_bom={}
    for point in record.capture.prepared.forecast.predictions:
        name=next(name for name,pid in products.items() if pid==point.product_id)
        for path,quantity in [('LOW',point.p25),('BASE',point.p50),('HIGH',point.p75)]:
            for line in source['recipes']:
                if line['product_id']!=name:continue
                key=(path,point.forecast_date,ingredients[line['ingredient_id']])
                expected_bom[key]=expected_bom.get(key,Fraction(0))+Fraction(quantity)*line['quantity']
    assert {(r.path_id,r.day,r.ingredient_id):Fraction(r.quantity) for r in record.result.bom.totals}==expected_bom
    retained=client.get(accepted.headers['Location']);assert retained.status_code==200,retained.text
    wire=retained.json()['data'];result=wire['result'];winner=result['winner_option_id']
    if case=='insufficient_budget':
        assert winner is None and record.outcome=='no_eligible_candidate',wire
    else:
        assert winner is not None and record.outcome=='recommendation_available',wire
        option=next(o for o in result['options'] if o['option_id']==winner)
        purchases=option['purchases']
        assert bool(purchases)==(case=='main')
        terms={ingredients[r['ingredient_id']]:r for r in DATA['workbooks'][config['file']]['supplier_terms']}
        expected_cost=0
        for purchase in purchases:
            term=terms[UUID(purchase['ingredient_id'])];packs=int(purchase['packs'])
            assert packs>=term['minimum_order_quantity']
            assert exact(purchase['quantity'])==packs*term['pack_size_base_quantity']
            assert purchase['arrival_date']==str(start+timedelta(days=term['lead_time_days']))
            assert purchase['expiry_date']==(str(start+timedelta(days=term['lead_time_days']+term['shelf_life_days']))
                if term['shelf_life_days'] is not None else None)
            assert exact(purchase['purchase_outlay'])==packs*term['pack_cost']
            expected_cost+=packs*term['pack_cost']
        assert exact(option['costs']['total'])==expected_cost<=int(config['budget'])
        assert all(exact(s['fulfilled'])==exact(s['requested']) and exact(s['lost_sales'])==0
                   for s in option['product_services'] if s['path']=='BASE')
        assert expected_cost>0 if case=='main' else expected_cost==0
        capacities={ingredients[r['ingredient_id']]:int(r['maximum_quantity'])
            for r in source['scope_declarations'][-1]['declaration']['capacities']}
        for ing in ingredients.values():
            stock=sum(r['quantity'] for r in source['opening_stock'] if ingredients[r['ingredient_id']]==ing)
            for offset in range(7):
                day=start+timedelta(days=offset)
                stock+=sum(exact(p['quantity']) for p in purchases if UUID(p['ingredient_id'])==ing and p['arrival_date']==str(day))
                assert stock<=capacities[ing]
                stock-=expected_bom['BASE',day,ing]
                assert stock>=0
            balance=next(b for b in option['ingredient_balances'] if b['ingredient_id']==str(ing) and b['path']=='BASE')
            assert exact(balance['consumed'])==sum(q for (path,day,i),q in expected_bom.items() if path=='BASE' and i==ing)
            assert exact(balance['ending_usable'])==stock
    with Session(c[0][1]) as fresh:
        assert fresh.scalar(select(func.max(SalesDaily.sales_date)))==CUTOFF
        assert fresh.scalar(select(func.count()).select_from(InventoryLot))==len(lots)
        for original in source['opening_stock']:
            assert fresh.get(InventoryLot,lots[original['lot_code']]).on_hand_quantity==original['quantity']
        row=fresh.get(PlanningRun,record.run_id)
        assert row.record_json['status']=='completed'
    save('synthetic-cafe-'+case,dict(case=case,manifest=DATA['manifest'],import_id=ident,
        workbook_sha256=hashlib.sha256((FIXTURE/config['file']).read_bytes()).hexdigest(),
        training_readiness=[r.model_dump(mode='json') for r in rows.readiness],
        evaluation=report.model_dump(mode='json') if report else None,
        artifact_identity=artifact_identity,
        candidate_forecast=candidate_forecast.model_dump(mode='json') if candidate_forecast else None,
        product_names={str(pid):name for name,pid in products.items()},
        baseline_forecast=record.capture.prepared.forecast.model_dump(mode='json'),
        bom=record.result.bom.model_dump(mode='json',exclude={'prepared'}),
        pipeline=wire,limits='SYNTHETIC; public supported serving BASELINE, internal rolling LightGBM evaluation separate. External actuals never imported or scored. Recommendation is not user selection or stock mutation.'))
