"""Public C3 import/worker/canonical N6 identity with fresh PostgreSQL reads."""
from uuid import UUID,uuid4
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from tests.integration.test_auth_public import env
from tests.integration.test_staff_public import staff_env
from tests.integration.test_planning_configuration_public import config
from tests.integration.test_planning_public import flow
from tests.integration.test_import_setup_stock import fresh_store,review_batch,complete
from tests.integration.test_import_staging import csv_source,previewed,post
from tests.integration.test_import_commit import analyzed_files
from app.application.use_cases.public_reads import PublicReads
from app.application.use_cases.stock_writes import StockWrites
from app.models import Ingredient,InventoryLot,InventoryMovement
from app.models.operational_import import InventoryReceiptRecord
from app.models.import_staging import ImportJob,ImportAudit,ImportProfile,ImportProfileVersion

CONTEXT=dict(source_system_key='RECEIPTS',report_type='actual-deliveries',inventory_semantics='actual_receipt')


def source(context,**changes):
    record=dict(source_record_id='DELIVERY-1',ingredient_id='MILK',supplier_id=None,lot_code='DELIVERY-LOT',
        quantity='1.25',unit='l',received_date=None,expiry_date=None,unit_cost=None,currency='VND',
        observed_at=context[0][4][0].isoformat(),reason='Explicit synthetic actual delivery')
    return {**record,**changes}


def configure_stock(context):
    reads=PublicReads(context[0][2]);context[0][5].app.state.public_reads=reads
    context[0][5].app.state.stock_writes=StockWrites(context[0][2],reads)


def review(context,ident,*,new=True,approve=True,bindings=None):
    review_batch(context,ident,creations={'MILK':('ingredient',dict(name='Synthetic actual milk',base_unit='l',sku='MILK',
        active=True,expiry_tracking=False))} if new else None,bindings=bindings,source_context=CONTEXT,approve_profiles=approve)


def test_excel_actual_receipt_shared_n6_identity_and_separate_commit(fresh_store):
    context=fresh_store;configure_stock(context);record=source(context)
    ident=analyzed_files(context,[('receipt.csv',csv_source('inventory_receipts',[record]))])
    review(context,ident)
    read=previewed(context,ident)
    row=next(r for r in read['preview']['rows'] if r['canonical_domain']=='inventory_receipts' or (r['after'] or {}).get('domain')=='inventory_receipts')
    assert row['receipt_effect']['action']=='CREATE_RECEIPT' and row['receipt_effect']['recorded_at'] is None
    with Session(context[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(InventoryLot))==0
        assert fresh.scalar(select(func.count()).select_from(Ingredient))==0
    from tests.integration.test_import_commit import confirm,commit,finished
    confirmed=confirm(context,ident,read);assert confirmed.status_code==200,confirmed.text
    done=finished(context,ident,commit(context,ident,read,confirmed.json()['data']['import_revision']))
    reference=next(r for r in done['canonical_references'] if r['canonical_domain']=='inventory_receipts')
    assert reference['receipt_reference']['action']=='CREATED'
    assert reference['receipt_effect']['receipt_id']==row['receipt_effect']['receipt_id']
    assert reference['receipt_effect']['movement_id']==row['receipt_effect']['movement_id']
    ingredient=row['after']['ingredient_id'];lot_id=row['receipt_effect']['lot_id']
    with Session(context[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(InventoryReceiptRecord))==1
        assert fresh.scalar(select(func.count()).select_from(InventoryMovement))==1
        lot=fresh.get(InventoryLot,UUID(lot_id));assert lot.on_hand_quantity==1.25 and lot.received_date is None
        movement=fresh.scalar(select(InventoryMovement));assert movement.movement_type=='RECEIPT' and movement.reference_type=='ACTUAL_RECEIPT'
    path=f'/api/v1/stores/{context[1].store_id}/inventory/{ingredient}'
    inventory=context[0][5].get(path);assert inventory.status_code==200,inventory.text
    assert inventory.json()['data']['on_hand_quantity']=='1.25'
    assert inventory.json()['data']['stock_completeness']=='UNKNOWN'
    body={k:v for k,v in record.items() if k!='source_record_id'}
    body.update(origin='ACTUAL_RECEIPT',ingredient_id=ingredient,receipt_identity=dict(source_system_key='RECEIPTS',source_record_id='DELIVERY-1'),
        expected_inventory_version='retained-replay-precedes-CAS')
    replay=context[0][5].post(f'/api/v1/stores/{context[1].store_id}/inventory/receipts',
        json=body,headers={**context[3],'Idempotency-Key':str(uuid4())})
    assert replay.status_code==200,replay.text
    assert replay.json()['data']['receipt_id']==reference['receipt_reference']['receipt_id']


def test_form_then_excel_reuses_receipt_without_new_inventory(fresh_store):
    context=fresh_store;configure_stock(context);ingredient=uuid4()
    with Session(context[0][1]) as s:
        s.add(Ingredient(id=ingredient,store_id=context[1].store_id,name='Synthetic known milk',base_unit='l',expiry_tracking=False,active=True));s.commit()
    record=source(context,ingredient_id=str(ingredient));body={k:v for k,v in record.items() if k!='source_record_id'}
    current=context[0][5].get(f'/api/v1/stores/{context[1].store_id}/inventory/{ingredient}').json()
    body.update(origin='ACTUAL_RECEIPT',receipt_identity=dict(source_system_key='RECEIPTS',source_record_id='DELIVERY-1'),
        expected_inventory_version=current['meta']['data_version'])
    created=context[0][5].post(f'/api/v1/stores/{context[1].store_id}/inventory/receipts',
        json=body,headers={**context[3],'Idempotency-Key':str(uuid4())})
    assert created.status_code==201,created.text
    ident=analyzed_files(context,[('different-name.csv',csv_source('inventory_receipts',[record,record]))])
    review(context,ident,new=False)
    read,done=complete(context,ident)
    assert len(read['preview']['rows'])==1 and len(read['preview']['rows'][0]['source_locations'])==2
    assert done['outcome']=='no_changes' and done['canonical_references'][0]['receipt_reference']['action']=='REUSED'
    with Session(context[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(InventoryLot))==1
        assert fresh.scalar(select(func.count()).select_from(InventoryMovement))==1
        assert fresh.scalar(select(func.count()).select_from(InventoryReceiptRecord))==1


def test_profile_reuse_reimport_conflict_and_retirement(fresh_store,monkeypatch):
    context=fresh_store;record=source(context)
    from app.infrastructure import import_suggestions
    monkeypatch.setattr(import_suggestions,'suggest_sheet',lambda *a,**k:pytest.fail('Receipt provider must remain OFF'))
    first=analyzed_files(context,[('original.csv',csv_source('inventory_receipts',[record]))]);review(context,first)
    complete(context,first)
    with Session(context[0][1]) as fresh:
        profile=fresh.scalar(select(ImportProfile));profile_id=profile.id
        ingredient_id=fresh.scalar(select(Ingredient.id))
        assert fresh.scalar(select(func.count()).select_from(ImportProfileVersion))==1
    second=analyzed_files(context,[('renamed.csv',csv_source('inventory_receipts',[record]))]);review(context,second,new=False)
    _,reused=complete(context,second);assert reused['outcome']=='no_changes'
    with Session(context[0][1]) as fresh: assert fresh.scalar(select(func.count()).select_from(ImportProfileVersion))==1
    changed=analyzed_files(context,[('changed.csv',csv_source('inventory_receipts',[{**record,'quantity':'2'}]))]);review(context,changed,new=False)
    conflict=previewed(context,changed)['preview']
    assert 'RECEIPT_IDENTITY_CONFLICT' in {b['code'] for b in conflict['summary']['blockers']}
    with Session(context[0][1]) as fresh:
        profile=fresh.get(ImportProfile,profile_id);active,revision=profile.active_version,profile.lifecycle_revision
    retired=post(context,f'/stores/{context[1].store_id}/mapping-profiles/{profile_id}/decisions',
        dict(decision='retire',active_version=active,reason='Explicit receipt profile retirement'),match=revision)
    assert retired.status_code==200,retired.text
    third=analyzed_files(context,[('after-retirement.csv',csv_source('inventory_receipts',[{**record,'source_record_id':'DELIVERY-2'}]))])
    review(context,third,new=False,approve=False,bindings={'MILK':ingredient_id})
    from tests.integration.test_import_field_value_bindings import summary
    assert not summary(context,third)['can_preview']
    with Session(context[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(InventoryReceiptRecord))==1


@pytest.mark.parametrize('reverse',(False,True))
def test_duplicate_receipts_across_uploads_coalesce_independent_of_order(fresh_store,reverse):
    context=fresh_store;record=source(context)
    files=[('first.csv',csv_source('inventory_receipts',[record])),('second.csv',csv_source('inventory_receipts',[record]))]
    ident=analyzed_files(context,list(reversed(files)) if reverse else files);review(context,ident)
    read,done=complete(context,ident)
    receipts=[r for r in read['preview']['rows'] if (r['after'] or {}).get('domain')=='inventory_receipts']
    assert len(receipts)==1 and len(receipts[0]['source_locations'])==2
    assert done['updated_resources']['inventory']['changed_record_count']==1
    with Session(context[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(InventoryReceiptRecord))==1
        assert fresh.scalar(select(func.count()).select_from(InventoryMovement))==1


def test_receipt_mq_owner_approval_keeps_inventory_empty_until_commit(fresh_store):
    context=fresh_store;ident=analyzed_files(context,[('queue.csv',csv_source('inventory_receipts',[source(context)]))])
    review(context,ident,approve=False)
    from tests.integration.test_mapping_submissions import submit
    response,profile,_=submit(context,ident);assert response.status_code==201,response.text
    row=response.json()['data'];base=f'/api/v1/stores/{context[1].store_id}/mapping-submissions'
    assert context[0][5].get(base).json()['data']['items'][0]['submission_id']==row['submission_id']
    today=f'/api/v1/stores/{context[1].store_id}/today?section=mapping'
    pending=context[0][5].get(today).json()['data']['sections']['mapping']['value']
    assert pending['total_count']==1 and pending['items'][0]['id']==row['submission_id']
    decided=post(context,f'/stores/{context[1].store_id}/mapping-profiles/{profile["profile_id"]}/decisions',
        dict(decision='approve_activate',proposal_revision=profile['proposal_revision'],expected_active_version=None,
            submission_id=row['submission_id'],expected_submission_version=row['version'],reason='Owner reviews actual receipt spec'),
        match=profile['lifecycle_revision'])
    assert decided.status_code==200,decided.text
    assert context[0][5].get(today).json()['data']['sections']['mapping']['value']['total_count']==0
    with Session(context[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(InventoryLot))==0
        from app.models.notifications import NotificationIntent
        assert fresh.scalar(select(func.count()).select_from(NotificationIntent))==2
    _,done=complete(context,ident);assert done['outcome']=='committed'


def test_mixed_receipt_fault_rolls_back_new_entities_and_all_inventory(fresh_store,monkeypatch):
    from app.models import Product
    from app.application.use_cases.inventory_receipts import InventoryReceipts
    from app.application.contracts.auth import AuthError
    context=fresh_store
    product=dict(source_business_key='COFFEE',name='Explicit other domain',sku='COFFEE',price=None,selling_unit='cup',active=True)
    ident=analyzed_files(context,[('products.csv',csv_source('products',[product])),
        ('receipt.csv',csv_source('inventory_receipts',[source(context)]))])
    review_batch(context,ident,creations={'MILK':('ingredient',dict(name='Synthetic milk',base_unit='l',sku='MILK',active=True,expiry_tracking=False)),
        'COFFEE':('product',dict(name='Explicit other domain',sku='COFFEE',price=None,selling_unit='cup',active=True))},source_context=CONTEXT)
    read=previewed(context,ident)
    from tests.integration.test_import_commit import confirm,commit
    confirmed=confirm(context,ident,read);assert confirmed.status_code==200
    original=InventoryReceipts.create
    def fail(self,*args,**kwargs):
        original(self,*args,**kwargs);raise AuthError('PREVIEW_BLOCKED',409)
    accepted=commit(context,ident,read,confirmed.json()['data']['import_revision']);assert accepted.status_code==202
    with monkeypatch.context() as patch:
        patch.setattr(InventoryReceipts,'create',fail);context[2].run_one()
    with Session(context[0][1]) as fresh:
        for model in (Product,Ingredient,InventoryLot,InventoryMovement,InventoryReceiptRecord):
            assert fresh.scalar(select(func.count()).select_from(model))==0
        assert fresh.get(ImportJob,UUID(accepted.json()['data']['job_id'])).status=='failed'


def test_receipt_uncertain_commit_reconciles_shared_ledger_without_repeat(fresh_store,monkeypatch):
    context=fresh_store;ident=analyzed_files(context,[('receipt.csv',csv_source('inventory_receipts',[source(context)]))]);review(context,ident)
    read=previewed(context,ident)
    from tests.integration.test_import_commit import confirm,commit,finished
    confirmed=confirm(context,ident,read);key=str(uuid4())
    accepted=commit(context,ident,read,confirmed.json()['data']['import_revision'],key=key)
    original=Session.commit;raised=[]
    def uncertain(s):
        successful=any(isinstance(r,ImportAudit) and r.kind=='IMPORT_CANONICAL_COMMITTED' for r in s.new)
        original(s)
        if successful and not raised:
            raised.append(True);raise RuntimeError('Synthetic lost receipt ACK after durable commit')
    with monkeypatch.context() as patch:
        patch.setattr(Session,'commit',uncertain);done=finished(context,ident,accepted)
    assert raised and context[2].run_one() is None
    replay=commit(context,ident,read,confirmed.json()['data']['import_revision'],key=key)
    assert replay.status_code==202 and replay.json()['data']==accepted.json()['data']
    with Session(context[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(InventoryReceiptRecord))==1
        assert fresh.scalar(select(func.count()).select_from(InventoryLot))==1
        assert fresh.scalar(select(func.count()).select_from(InventoryMovement))==1


def test_actual_xlsx_source_locations_and_known_zero_cost(fresh_store):
    from xml.sax.saxutils import escape
    from tests.unit.test_import_parser import workbook
    context=fresh_store;record=dict(reversed(list(source(context,unit_cost='0').items())))
    def cells(values,number):
        return f'<row r="{number}">'+''.join(f'<c r="{chr(65+i)}{number}" t="inlineStr"><is><t>{escape(str(value) if value is not None else "")}</t></is></c>'
            for i,value in enumerate(values))+'</row>'
    content=workbook(cells(['Explicit receipt source'],1)+cells(['inventory_receipts.'+k for k in record],3)+cells(record.values(),4))
    ident=analyzed_files(context,[('actual-delivery.xlsx',content)]);review(context,ident)
    read,done=complete(context,ident)
    receipt=next(r for r in read['preview']['rows'] if (r['after'] or {}).get('domain')=='inventory_receipts')
    assert receipt['source_location']['row_number']==4
    assert receipt['after']['unit_cost']=='0' and receipt['after']['received_date'] is None
    assert receipt['provenance']['quantity']['source_value']=='1.25'
    assert receipt['provenance']['quantity']['source_column_index'] is not None
    with Session(context[0][1]) as fresh: assert fresh.scalar(select(InventoryLot)).unit_cost==0


def test_intervening_form_receipt_makes_import_preview_stale(fresh_store):
    context=fresh_store;configure_stock(context);ingredient=uuid4()
    with Session(context[0][1]) as s:
        s.add(Ingredient(id=ingredient,store_id=context[1].store_id,name='Explicit known milk',base_unit='l',active=True,expiry_tracking=False));s.commit()
    record=source(context,ingredient_id=str(ingredient))
    ident=analyzed_files(context,[('receipt.csv',csv_source('inventory_receipts',[record]))]);review(context,ident,new=False)
    read=previewed(context,ident)
    current=context[0][5].get(f'/api/v1/stores/{context[1].store_id}/inventory/{ingredient}').json()
    body={k:v for k,v in record.items() if k!='source_record_id'}
    body.update(origin='ACTUAL_RECEIPT',receipt_identity=dict(source_system_key='RECEIPTS',source_record_id='INTERVENING'),
        expected_inventory_version=current['meta']['data_version'])
    created=context[0][5].post(f'/api/v1/stores/{context[1].store_id}/inventory/receipts',json=body,
        headers={**context[3],'Idempotency-Key':str(uuid4())})
    assert created.status_code==201,created.text
    from tests.integration.test_import_commit import confirm
    stale=confirm(context,ident,read);assert stale.status_code==409 and stale.json()['error']['code']=='PREVIEW_STALE'
    with Session(context[0][1]) as fresh: assert fresh.scalar(select(func.count()).select_from(InventoryReceiptRecord))==1


@pytest.fixture
def staff_receipt(staff_env):
    from tests.integration.test_staff_public import create,accept_http,target_session
    from app.domain.permissions import PERMISSIONS
    from app.application.use_cases.import_staging import ImportStaging
    ctx=staff_env;invitation,raw=create(ctx,grants=tuple(sorted(PERMISSIONS)))
    assert accept_http(ctx,invitation,raw).status_code==201
    token,csrf=target_session(ctx);service=ImportStaging(ctx[0][2],ctx[0][0]);ctx[0][5].app.state.import_staging=service
    context=ctx[0],ctx[2],service,{'Origin':ctx[5]['Origin'],'X-CSRF-Token':csrf},None
    ingredient=uuid4()
    with Session(ctx[0][1]) as s:
        s.add(Ingredient(id=ingredient,store_id=ctx[2].store_id,name='Explicit Staff receipt ingredient',base_unit='l',active=True,expiry_tracking=False));s.commit()
    return ctx,context,ingredient,token


@pytest.mark.parametrize('cost',(None,'0'))
def test_staff_receipt_current_cost_rights_and_owner_queue(staff_receipt,cost):
    from tests.integration.test_staff_public import owner_session
    from app.application.contracts.staff import GrantsRequest
    from app.domain.permissions import PERMISSIONS
    from tests.integration.test_mapping_submissions import submit
    ctx,context,ingredient,old_token=staff_receipt
    record=source(context,ingredient_id=str(ingredient),unit_cost=cost)
    ident=analyzed_files(context,[('staff-receipt.csv',csv_source('inventory_receipts',[record]))])
    # Staff resolves source/mapping, but activation remains the existing Owner N5.
    review(context,ident,new=False,approve=False)
    submitted,profile,_=submit(context,ident);assert submitted.status_code==201,submitted.text
    row=submitted.json()['data'];owner_session(ctx)
    owner=ctx[0],ctx[2],context[2],ctx[5],None
    approval=post(owner,f'/stores/{ctx[2].store_id}/mapping-profiles/{profile["profile_id"]}/decisions',
        dict(decision='approve_activate',proposal_revision=profile['proposal_revision'],expected_active_version=None,
            submission_id=row['submission_id'],expected_submission_version=row['version'],reason='Owner reviews Staff receipt profile'),match=profile['lifecycle_revision'])
    assert approval.status_code==200,approval.text
    member=ctx[1].memberships(ctx[4],ctx[2].store_id)[0].items[0]
    ctx[1].replace(ctx[4],ctx[2].store_id,member.membership_id,GrantsRequest(grants=tuple(sorted(PERMISSIONS-{'procurement.cost.read','supplier.read'})),
        reason='Explicit source-sensitive permission restriction'),str(uuid4()),member.version,ctx[5]['X-CSRF-Token'],'receipt-test')
    ctx[0][5].cookies.set('__Host-shelfcash_session',old_token,domain='backend.example.test',path='/')
    read=ctx[0][5].get('/api/v1/imports/'+ident+'?include=configurations')
    if cost is not None:
        assert read.status_code==403
        assert ctx[0][5].get(f'/api/v1/stores/{ctx[2].store_id}/mapping-submissions/{row["submission_id"]}').status_code==403
    else:
        assert read.status_code==200,read.text
        _,done=complete(context,ident);assert done['outcome']=='committed'
    with Session(ctx[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(InventoryReceiptRecord))==(0 if cost is not None else 1)


def test_receipt_worker_rechecks_revoke_after_acceptance(staff_receipt):
    from tests.integration.test_staff_public import owner_session
    from app.application.contracts.staff import GrantsRequest
    from app.domain.permissions import PERMISSIONS
    from tests.integration.test_import_commit import confirm,commit
    ctx,context,ingredient,old_token=staff_receipt
    ident=analyzed_files(context,[('receipt.csv',csv_source('inventory_receipts',[source(context,ingredient_id=str(ingredient))]))])
    review(context,ident,new=False,approve=False)
    from tests.integration.test_import_field_value_bindings import summary
    profile=summary(context,ident)['profile_proposals'][0]
    owner_session(ctx);owner=ctx[0],ctx[2],context[2],ctx[5],None
    approved=post(owner,f'/stores/{ctx[2].store_id}/mapping-profiles/{profile["profile_id"]}/decisions',
        dict(decision='approve_activate',proposal_revision=profile['proposal_revision'],expected_active_version=None,reason='Explicit receipt profile approval'),
        match=profile['lifecycle_revision']);assert approved.status_code==200,approved.text
    ctx[0][5].cookies.set('__Host-shelfcash_session',old_token,domain='backend.example.test',path='/')
    read=previewed(context,ident);confirmed=confirm(context,ident,read)
    accepted=commit(context,ident,read,confirmed.json()['data']['import_revision']);assert accepted.status_code==202
    owner_session(ctx);member=ctx[1].memberships(ctx[4],ctx[2].store_id)[0].items[0]
    ctx[1].replace(ctx[4],ctx[2].store_id,member.membership_id,GrantsRequest(grants=tuple(sorted(PERMISSIONS-{'inventory.receive'})),
        reason='Explicit revoke before receipt worker'),str(uuid4()),member.version,ctx[5]['X-CSRF-Token'],'receipt-revoke')
    context[2].run_one()
    with Session(ctx[0][1]) as fresh:
        job=fresh.get(ImportJob,UUID(accepted.json()['data']['job_id']))
        assert job.status=='failed' and job.error_json['code']=='PERMISSION_DENIED'
        for model in (InventoryReceiptRecord,InventoryLot,InventoryMovement):
            assert fresh.scalar(select(func.count()).select_from(model))==0


def test_concurrent_receipt_jobs_share_identity_then_stale_batch_requires_refresh(fresh_store):
    from tests.integration.test_import_commit import confirm,commit
    context=fresh_store;ingredient=uuid4()
    with Session(context[0][1]) as s:
        s.add(Ingredient(id=ingredient,store_id=context[1].store_id,name='Explicit race ingredient',base_unit='l',active=True,expiry_tracking=False));s.commit()
    record=source(context,ingredient_id=str(ingredient));accepted=[];prepared=[]
    for filename in ('one.csv','two.csv'):
        ident=analyzed_files(context,[(filename,csv_source('inventory_receipts',[record]))]);review(context,ident,new=False)
        read=previewed(context,ident);confirmed=confirm(context,ident,read)
        prepared.append((ident,read,confirmed.json()['data']['import_revision']))
    for ident,read,revision in prepared:
        response=commit(context,ident,read,revision);assert response.status_code==202
        accepted.append(response.json()['data']['job_id'])
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _:context[2].run_one(),range(2)))
    # Concurrent callers may contend for one bounded candidate; resume the queue
    # through the normal worker instead of assuming each call claims a different job.
    context[2].run_one()
    with Session(context[0][1]) as fresh:
        jobs=[fresh.get(ImportJob,UUID(identity)) for identity in accepted]
        assert sorted(j.status for j in jobs)==['completed','failed']
        assert next(j for j in jobs if j.status=='failed').error_json['code']=='PREVIEW_STALE'
        assert fresh.scalar(select(func.count()).select_from(InventoryReceiptRecord))==1
        assert fresh.scalar(select(func.count()).select_from(InventoryLot))==1


def test_receipt_updates_fresh_capture_and_keeps_retained_planning_run(flow):
    from datetime import date
    from decimal import Decimal
    from app.models import SalesDaily,PlanningRun
    from app.application.use_cases.import_staging import ImportStaging
    from tests.integration.test_readiness_context import declaration
    from tests.integration.test_planning_public import submit as submit_plan
    from app.application.contracts import import_domains as domains
    from app.infrastructure.database.decision_capture_v2 import PostgresDecisionSnapshotSourceV2
    c,ingredient,recipe,worker=flow;lot_id=uuid4()
    with Session(c[0][1]) as s:
        s.scalar(select(SalesDaily)).quantity=5
        s.add(InventoryLot(id=lot_id,store_id=c[1].store_id,ingredient_id=ingredient,received_date=date(2026,10,9),expiry_date=None,
            on_hand_quantity=100,unit='ml',unit_cost=1));s.flush()
        declaration(s,c[1].store_id,domains.InventoryDeclaration(kind='INVENTORY',ingredient_id=ingredient,state='COMPLETE_CURRENT_LOTS',
            observed_at=c[0][4][0],covered_lot_ids=(lot_id,),evidence_reference='Explicit synthetic physical100'),'inventory');s.commit()
    accepted=submit_plan(c);assert accepted.status_code==202,accepted.text
    retained=worker.run_one();assert retained.status=='completed',retained.error_code
    before=c[0][5].get(accepted.headers['Location']).json()['data']
    with Session(c[0][1]) as fresh: original=fresh.get(PlanningRun,retained.run_id).record_json
    service=ImportStaging(c[0][2],c[0][0]);c[0][5].app.state.import_staging=service
    context=c[0],c[1],service,c[3],c[2]
    ident=analyzed_files(context,[('receipt.csv',csv_source('inventory_receipts',[source(context,ingredient_id=str(ingredient),unit='ml',quantity='5')]))])
    review(context,ident,new=False);_,done=complete(context,ident)
    captured=PostgresDecisionSnapshotSourceV2(c[0][1]).read(retained.capture.request,lambda:c[0][4][0])
    assert sum(l.on_hand_quantity for l in captured.facts.lots)==Decimal('105')
    assert c[0][5].get(accepted.headers['Location']).json()['data']==before
    with Session(c[0][1]) as fresh:
        assert fresh.get(PlanningRun,retained.run_id).record_json==original
        assert fresh.get(InventoryLot,lot_id).on_hand_quantity==100
    # Receiving stock invalidates prior completeness evidence; it does not claim coverage.
    from app.repositories.readiness import load_readiness
    from app.application.operational_import_facts import inventory_matches
    from app.application.readiness_evaluation import latest_declarations
    with Session(c[0][1]) as fresh:
        facts=load_readiness(fresh,c[1].store_id)
        assert inventory_matches(facts.snapshot,latest_declarations(facts.snapshot),ingredient,c[0][4][0])==()


@pytest.mark.parametrize('field',('ingredient_id','supplier_id'))
def test_receipt_foreign_identity_binding_is_scope_safe(fresh_store,field):
    from app.models import Store,Supplier
    from tests.integration.test_import_rule_review import declare_context
    from tests.integration.test_import_classification import mapping,listing
    context=fresh_store;foreign,foreign_ingredient,foreign_supplier,own=uuid4(),uuid4(),uuid4(),uuid4()
    with Session(context[0][1]) as s:
        s.add(Store(id=foreign,name='Explicit foreign test Store'));s.flush()
        s.add_all([Ingredient(id=foreign_ingredient,store_id=foreign,name='Foreign ingredient',base_unit='l',active=True,expiry_tracking=False),
            Supplier(id=foreign_supplier,store_id=foreign,name='Foreign supplier',active=True),
            Ingredient(id=own,store_id=context[1].store_id,name='Own ingredient',base_unit='l',active=True,expiry_tracking=False)]);s.commit()
    forbidden=foreign_ingredient if field=='ingredient_id' else foreign_supplier
    record=source(context,ingredient_id=str(own));record[field]=str(forbidden)
    ident=analyzed_files(context,[('foreign.csv',csv_source('inventory_receipts',[record]))])
    declare_context(context,ident,CONTEXT)
    issue=next(i for i in listing(context,ident) if i['issue_type']=='identity' and i['source_header']==str(forbidden))
    result=mapping(context,ident,issue,{'resolution':dict(kind='identity_binding',canonical_id=str(forbidden))})
    assert result.status_code==404,result.text
    with Session(context[0][1]) as fresh:
        for model in (InventoryLot,InventoryMovement,InventoryReceiptRecord):
            assert fresh.scalar(select(func.count()).select_from(model))==0


def test_new_receipt_file_does_not_delete_absent_receipt_or_reuse_lot_label(fresh_store):
    context=fresh_store;record=source(context)
    ident=analyzed_files(context,[('one.csv',csv_source('inventory_receipts',[record]))]);review(context,ident);complete(context,ident)
    second=analyzed_files(context,[('two.csv',csv_source('inventory_receipts',[{**record,'source_record_id':'DELIVERY-2'}]))])
    review(context,second,new=False);_,done=complete(context,second)
    assert done['updated_resources']['inventory']['changed_record_count']==1
    with Session(context[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(InventoryReceiptRecord))==2
        lots=fresh.scalars(select(InventoryLot)).all()
        assert len(lots)==2 and sum(l.on_hand_quantity for l in lots)==2.5
        assert {l.lot_code for l in lots}=={'DELIVERY-LOT'}


def test_receipt_store_day_rollover_requires_new_preview(fresh_store):
    from tests.integration.test_auth_public import login
    from tests.integration.test_import_commit import confirm
    context=fresh_store;ident=analyzed_files(context,[('receipt.csv',csv_source('inventory_receipts',[source(context)]))]);review(context,ident)
    read=previewed(context,ident)
    context[0][4][0]+=timedelta(days=1)
    context[3]['X-CSRF-Token']=login(context[0]).json()['data']['session']['csrf_token']
    stale=confirm(context,ident,read)
    assert stale.status_code==409 and stale.json()['error']['code']=='PREVIEW_STALE'
    with Session(context[0][1]) as fresh: assert fresh.scalar(select(func.count()).select_from(InventoryReceiptRecord))==0


def test_receipt_spec_change_uses_existing_queue_and_stale_decision_fence(fresh_store):
    from tests.integration.test_import_rule_review import declare_context,summary
    from tests.integration.test_mapping_submissions import submit
    context=fresh_store;record=source(context)
    first=analyzed_files(context,[('one.csv',csv_source('inventory_receipts',[record]))]);review(context,first);complete(context,first)
    second=analyzed_files(context,[('two.csv',csv_source('inventory_receipts',[record]))]);review(context,second,new=False)
    changed=declare_context(context,second,{**CONTEXT,'date_format':'ISO'})
    assert not changed['can_preview']
    pending,profile,_=submit(context,second);assert pending.status_code==201,pending.text
    old=pending.json()['data']
    declare_context(context,second,{**CONTEXT,'date_format':'DMY_SLASH'})
    current=summary(context,second)['profile_proposals'][0]
    rejected=post(context,f'/stores/{context[1].store_id}/mapping-profiles/{current["profile_id"]}/decisions',
        dict(decision='approve_activate',proposal_revision=current['proposal_revision'],expected_active_version=current['active_version'],
            submission_id=old['submission_id'],expected_submission_version=old['version'],reason='Stale receipt date interpretation'),
        match=current['lifecycle_revision'])
    assert rejected.status_code==409 and rejected.json()['error']['code']=='MAPPING_SUBMISSION_STALE'
    pending,current,_=submit(context,second);assert pending.status_code==201,pending.text
    row=pending.json()['data']
    approved=post(context,f'/stores/{context[1].store_id}/mapping-profiles/{current["profile_id"]}/decisions',
        dict(decision='approve_activate',proposal_revision=current['proposal_revision'],expected_active_version=current['active_version'],
            submission_id=row['submission_id'],expected_submission_version=row['version'],reason='Owner reviews changed receipt interpretation'),
        match=current['lifecycle_revision'])
    assert approved.status_code==200,approved.text
    _,done=complete(context,second);assert done['outcome']=='no_changes'
    with Session(context[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(InventoryReceiptRecord))==1
        assert fresh.scalar(select(func.count()).select_from(ImportProfileVersion))==2
