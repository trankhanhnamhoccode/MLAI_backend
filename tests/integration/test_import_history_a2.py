"""A2 public mapping/review/atomic commit with owned PostgreSQL and fresh reads."""
from uuid import UUID, uuid4
import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from tests.integration.test_auth_public import env
from tests.integration.test_import_staging import imp, csv_source, post, analyzed, approved, previewed
from tests.integration.test_import_commit import ready, finished, analyzed_files
from tests.integration.test_import_classification import confirm
from app.models import Ingredient, ImportHistoryRecord, InventoryLot, InventoryMovement, SupplierTerm, SalesDaily, StoreMembership
from app.models.auth import MembershipGrant
from app.models.import_staging import ImportJob, ImportAudit
from app.domain.permissions import PERMISSIONS
from tests.unit.test_import_history_a2 import purchase, usage
from tests.integration.test_import_setup_stock import fresh_store, review_batch


@pytest.fixture
def ingredient(imp):
    ident=uuid4()
    with Session(imp[0][1]) as session:
        session.add(Ingredient(id=ident,store_id=imp[1].store_id,name='Synthetic flour',base_unit='g',
            active=True,expiry_tracking=False));session.commit()
    return ident


def records(schema, imp, ingredient):
    if schema=='usage_history': return usage(ingredient)
    if schema=='purchase_history': return purchase(ingredient)
    if schema=='calendar_events': return dict(source_record_key='event-1',evidence_reference='Owner known announcement',
        event_name='Holiday',effective_from='2027-01-01',effective_to='2027-01-02',
        declared_at='2026-10-09T01:00:00Z',is_closed=False,is_holiday=None)
    return dict(source_record_key='promotion-1',evidence_reference='POS observed',product_id=str(imp[4]),
        sales_date='2026-10-09',promotion_name='CTKM A',promotion_applied=None)


def accept(imp, ident, read, rev, *, corrections=(), key=None, reason='Synthetic reviewed history'):
    return post(imp,'/imports/'+ident+'/process',dict(phase='commit',confirm=True,
        preview_id=read['preview']['summary']['preview_id'],preview_digest=read['preview']['summary']['digest'],
        reason=reason,resolutions=[],history_corrections=list(corrections)),match=rev,key=key)


@pytest.mark.parametrize('schema',['calendar_events','promotion_observations','usage_history','purchase_history'])
def test_roundtrip_no_inventory_inbound_or_terms_reuse_noop_and_correction(imp,ingredient,schema):
    record=records(schema,imp,ingredient)
    ident,read,rev=ready(imp,csv_source(schema,[record]))
    result=finished(imp,ident,accept(imp,ident,read,rev))
    evidence=result['canonical_references'][0]
    category={'calendar_events':'calendar','promotion_observations':'sales',
        'usage_history':'usage','purchase_history':'purchase'}[schema]
    from app.application.use_cases.import_history import ImportHistoryReads
    imp[0][5].app.state.import_history=ImportHistoryReads(imp[2])
    history=imp[0][5].get('/api/v1/stores/'+str(imp[1].store_id)+'/imports',
        params={'import_date':'2026-10-10','category':category})
    assert history.status_code==200,history.text
    assert ident in {item['import_id'] for item in history.json()['data']['items']}
    assert evidence['canonical_version']=='1' and evidence['movement_ids']==[]
    assert evidence['history_record']==read['preview']['rows'][0]['after']
    with Session(imp[0][1]) as fresh:
        row=fresh.scalar(select(ImportHistoryRecord))
        assert row.payload==evidence['history_record'] and row.version==1 and row.report_type=='daily-sales'
        for model in (InventoryLot,InventoryMovement,SupplierTerm,SalesDaily):
            assert fresh.scalar(select(func.count()).select_from(model))==0
    # Different filename and header order; declare source before exact reusable profile can be considered.
    reordered=dict(reversed(list(record.items())))
    second,read2,rev2=ready(imp,csv_source(schema,[reordered]))
    assert read2['preview']['rows'][0]['proposed_action']=='NO_OP'
    finished(imp,second,accept(imp,second,read2,rev2))
    changed=dict(record)
    field={'calendar_events':'event_name','promotion_observations':'promotion_name',
           'usage_history':'quantity','purchase_history':'price'}[schema]
    changed[field]='Renamed explicit event' if field.endswith('name') else '12'
    third,read3,rev3=ready(imp,csv_source(schema,[changed]))
    row=read3['preview']['rows'][0]
    assert row['proposed_action']=='CORRECT_HISTORY_RECORD' and row['expected_version']=='1'
    rejected=accept(imp,third,read3,rev3)
    assert rejected.status_code==409 and rejected.json()['error']['code']=='HISTORY_CORRECTION_UNRESOLVED'
    confirmation=dict(row_id=row['row_id'],expected_version='1',reason='Reviewed source correction')
    key=str(uuid4()); response=accept(imp,third,read3,rev3,corrections=[confirmation],key=key)
    corrected=finished(imp,third,response)
    assert corrected['canonical_references'][0]['canonical_version']=='2'
    assert accept(imp,third,read3,rev3,corrections=[confirmation],key=key).json()['data']==response.json()['data']
    with Session(imp[0][1]) as fresh:
        rows=fresh.scalars(select(ImportHistoryRecord).order_by(ImportHistoryRecord.version)).all()
        assert len(rows)==2 and rows[0].payload==evidence['history_record']
        assert rows[1].payload[field]==changed[field]
        assert fresh.scalar(select(func.count()).select_from(InventoryMovement))==0
    assert imp[0][5].get('/api/v1/imports/'+ident+'/completion').json()['data']==result


@pytest.mark.parametrize('schema,revoked',[('calendar_events','calendar.write'),('usage_history','usage.history.write'),
    ('purchase_history','purchase.history.write'),('purchase_history','procurement.cost.read'),
    ('calendar_events','calendar.read'),('usage_history','usage.history.read'),('purchase_history','purchase.history.read')])
def test_current_domain_rights_rechecked_worker_no_profile_grant(imp,ingredient,schema,revoked):
    ident,read,rev=ready(imp,csv_source(schema,[records(schema,imp,ingredient)]))
    response=accept(imp,ident,read,rev);assert response.status_code==202,response.text
    with Session(imp[0][1]) as s:
        member=s.scalar(select(StoreMembership).where(StoreMembership.store_id==imp[1].store_id));member.role='STAFF'
        for key in sorted(PERMISSIONS-{revoked}):s.add(MembershipGrant(membership_id=member.id,permission=key))
        s.commit()
    imp[2].run_one()
    with Session(imp[0][1]) as fresh:
        job=fresh.get(ImportJob,UUID(response.json()['data']['job_id']))
        assert job.status=='failed' and job.error_json['code']=='PERMISSION_DENIED'
        assert fresh.scalar(select(func.count()).select_from(ImportHistoryRecord))==0
    if revoked=='procurement.cost.read':
        assert imp[0][5].get('/api/v1/imports/'+ident+'/completion').status_code==403


def test_existing_staff_sales_analysis_does_not_need_new_history_grants(imp):
    from tests.integration.test_import_staging import sales_bytes
    added={'calendar.read','calendar.write','usage.history.read','usage.history.write',
        'purchase.history.read','purchase.history.write'}
    with Session(imp[0][1]) as s:
        member=s.scalar(select(StoreMembership).where(StoreMembership.store_id==imp[1].store_id));member.role='STAFF'
        for key in sorted(PERMISSIONS-added):s.add(MembershipGrant(membership_id=member.id,permission=key))
        s.commit()
    ident=analyzed(imp,sales_bytes(imp))
    response=imp[0][5].get('/api/v1/imports/'+ident+'/mapping-summary')
    assert response.status_code==200,response.text


def test_history_writer_failure_rolls_back_entire_mixed_batch(imp,ingredient,monkeypatch):
    ident=analyzed_files(imp,[('usage.csv',csv_source('usage_history',[usage(ingredient)])),
        ('purchase.csv',csv_source('purchase_history',[purchase(ingredient)]))])
    approved(imp,ident)
    summary=imp[0][5].get('/api/v1/imports/'+ident+'/mapping-summary').json()['data']
    for p in summary['profile_proposals']:
        if p['active_version'] is None:
            r=post(imp,'/stores/'+str(imp[1].store_id)+'/mapping-profiles/'+p['profile_id']+'/decisions',
                dict(decision='approve_activate',proposal_revision=p['proposal_revision'],expected_active_version=None,
                     reason='Mixed synthetic domain review'),match=p['lifecycle_revision'])
            assert r.status_code==200,r.text
    read=previewed(imp,ident);confirmed=confirm(imp,ident,read);assert confirmed.status_code==200,confirmed.text
    from app.application.use_cases import import_history_write
    original=import_history_write.write_history
    count=[0]
    def fail_second(*args,**kwargs):
        count[0]+=1
        if count[0]==2:
            from app.application.contracts.auth import AuthError
            raise AuthError('PREVIEW_STALE',409)
        return original(*args,**kwargs)
    monkeypatch.setattr(import_history_write,'write_history',fail_second)
    response=accept(imp,ident,read,confirmed.json()['data']['import_revision'])
    assert response.status_code==202,response.text
    imp[2].run_one()
    with Session(imp[0][1]) as fresh:
        assert count[0]==2
        assert fresh.scalar(select(func.count()).select_from(ImportHistoryRecord))==0
        assert fresh.scalar(select(func.count()).select_from(ImportAudit).where(ImportAudit.kind=='IMPORT_CANONICAL_COMMITTED'))==0
    monkeypatch.setattr(import_history_write,'write_history',original)
    retry,review,revision=ready(imp,csv_source('usage_history',[usage(ingredient)]))
    finished(imp,retry,accept(imp,retry,review,revision))
    with Session(imp[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(ImportHistoryRecord))==1


def test_calendar_and_observed_promotion_do_not_change_forecast_capture(imp,ingredient):
    from datetime import date
    from app.application.contracts.forecast_execution import ForecastExecutionInput
    from app.application.use_cases.forecast_execution import ForecastExecutionUseCases
    from app.application.forecast_serialization import serialize_prepared
    with Session(imp[0][1]) as s:
        s.add(SalesDaily(id=uuid4(),store_id=imp[1].store_id,product_id=imp[4],sales_date=date(2026,10,9),
            quantity=10,is_stockout=False));s.commit()
    service=ForecastExecutionUseCases(imp[0][1]);request=ForecastExecutionInput(store_id=imp[1].store_id,
        product_ids=(imp[4],),history_start_date=date(2026,10,9),cutoff_date=date(2026,10,9))
    before=serialize_prepared(service.capture(request))
    for schema in ('calendar_events','promotion_observations'):
        ident,read,revision=ready(imp,csv_source(schema,[records(schema,imp,ingredient)]))
        finished(imp,ident,accept(imp,ident,read,revision))
    assert serialize_prepared(service.capture(request))==before


def test_history_correction_concurrency_is_stale_not_duplicate_revision(imp,ingredient):
    from concurrent.futures import ThreadPoolExecutor
    from app.application.use_cases.import_staging import ImportStaging
    record=usage(ingredient)
    ident,read,revision=ready(imp,csv_source('usage_history',[record]))
    finished(imp,ident,accept(imp,ident,read,revision))
    plans=[]
    for q in ('2','3'):
        ident,read,revision=ready(imp,csv_source('usage_history',[dict(record,quantity=q)]))
        row=read['preview']['rows'][0]
        plans.append((ident,read,revision,[dict(row_id=row['row_id'],expected_version='1',reason='Reviewed correction')]))
    responses=[accept(imp,i,r,v,corrections=c) for i,r,v,c in plans]
    assert all(r.status_code==202 for r in responses)
    other=ImportStaging(imp[0][2],imp[2].settings)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures=[executor.submit(service.run_one) for service in (imp[2],other)]
        for future in futures:future.result()
    # One process permits one running canonical commit; the losing poll may
    # leave its job queued until the next worker tick, then its read set is stale.
    imp[2].run_one()
    with Session(imp[0][1]) as fresh:
        jobs=[fresh.get(ImportJob,UUID(r.json()['data']['job_id'])) for r in responses]
        assert sorted(j.status for j in jobs)==['completed','failed']
        assert next(j for j in jobs if j.status=='failed').error_json['code']=='PREVIEW_STALE'
        rows=fresh.scalars(select(ImportHistoryRecord).order_by(ImportHistoryRecord.version)).all()
        assert [r.version for r in rows]==[1,2] and rows[1].payload['quantity'] in {'2','3'}


@pytest.mark.parametrize('schema',['calendar_events','usage_history','purchase_history'])
def test_explicit_staff_domain_grant_allows_commit_and_readback(imp,ingredient,schema):
    ident,read,revision=ready(imp,csv_source(schema,[records(schema,imp,ingredient)]))
    needed=set(read['preview']['summary']['required_actions']) | {
        'import.commit','import.read','import.preview','mapping.read','ingredient.read',
        'inventory.read','menu.read','supplier.read','sales.read','procurement.cost.read',
        'calendar.read','usage.history.read','purchase.history.read'}
    with Session(imp[0][1]) as s:
        member=s.scalar(select(StoreMembership).where(StoreMembership.store_id==imp[1].store_id));member.role='STAFF'
        for key in sorted(needed):s.add(MembershipGrant(membership_id=member.id,permission=key))
        s.commit()
    result=finished(imp,ident,accept(imp,ident,read,revision))
    assert result['canonical_references'][0]['history_record']['domain']==schema
    assert 'inventory.receive' not in needed and 'inventory.count.correct' not in needed


def test_foreign_ingredient_and_foreign_completion_are_denied(imp,ingredient):
    from tests.integration.test_auth_public import setup,login
    other=setup(imp[0],'other-owner@example.test')
    foreign=uuid4()
    with Session(imp[0][1]) as s:
        s.add(Ingredient(id=foreign,store_id=other.store_id,name='Foreign flour',base_unit='g',active=True,expiry_tracking=False));s.commit()
    ident=analyzed(imp,csv_source('usage_history',[usage(foreign)]))
    from tests.integration.test_import_classification import listing,mapping
    identity=next(i for i in listing(imp,ident) if i['issue_type']=='identity')
    assert identity['code']=='UNKNOWN_INGREDIENT'
    denied=mapping(imp,ident,identity,dict(resolution=dict(kind='identity_binding',canonical_id=str(foreign))))
    assert denied.status_code==404,denied.text
    own,review,revision=ready(imp,csv_source('usage_history',[usage(ingredient)]))
    finished(imp,own,accept(imp,own,review,revision))
    login(imp[0],'other-owner@example.test')
    response=imp[0][5].get('/api/v1/imports/'+own+'/completion')
    assert response.status_code in {403,404} and response.json()['data'] is None


@pytest.mark.parametrize('reverse',[False,True])
def test_history_depends_on_reviewed_master_across_file_order(fresh_store,reverse):
    c=fresh_store
    metadata=dict(name='Synthetic imported flour',base_unit='g',sku=None,active=True,expiry_tracking=False)
    master=dict(source_business_key='FLOUR',**metadata)
    record=usage('FLOUR');record['quantity']='5'
    files=[('usage.csv',csv_source('usage_history',[record])),('ingredients.csv',csv_source('ingredients',[master]))]
    ident=analyzed_files(c,list(reversed(files)) if reverse else files)
    review_batch(c,ident,creations={'FLOUR':('ingredient',metadata)})
    read=previewed(c,ident)
    assert not read['preview']['summary']['blockers'],read['preview']
    history=next(r for r in read['preview']['rows'] if r['after']['domain']=='usage_history')
    master=next(r for r in read['preview']['rows'] if r['after']['domain']=='ingredients')
    assert history['dependencies']==[master['row_id']]
    response=confirm(c,ident,read);assert response.status_code==200,response.text
    result=finished(c,ident,accept(c,ident,read,response.json()['data']['import_revision']))
    with Session(c[0][1]) as fresh:
        row=fresh.scalar(select(ImportHistoryRecord));ingredient=fresh.scalar(select(Ingredient))
        assert row.payload['ingredient_id']==str(ingredient.id) and row.payload['quantity']=='5'
        assert fresh.scalar(select(func.count()).select_from(InventoryMovement))==0
