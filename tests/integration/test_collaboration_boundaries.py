"""Linked C2 continuation, isolation, current authority and uncertain commit."""
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID,uuid4
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError,IntegrityError,DBAPIError
import pytest
from tests.integration.test_auth_public import env,setup,ORIGIN,PASSWORD
from tests.integration.test_staff_public import staff_env,create,accept_http,target_session,owner_session
from tests.integration.test_import_staging import imp,analyzed,post,previewed
from tests.integration.test_import_rule_review import summary,declare_context
from tests.integration.test_mapping_submissions import submit
from tests.integration.test_permission_requests import prepare,submit as permission_submit
from app.application.contracts.auth import LoginRequest
from app.application.use_cases.import_staging import ImportStaging
from app.application.use_cases.notification_delivery import NotificationDispatcher
from app.domain.permissions import PERMISSIONS
from app.models import Product,SalesDaily,StoreMembership
from app.models.import_staging import ImportBatch,ImportProfileVersion,ImportReceipt
from app.models.collaboration import MappingSubmissionRecord,PermissionRequestRecord,PermissionRequestAudit


def staff_import(ctx):
    data,raw=create(ctx,grants=tuple(sorted(PERMISSIONS)))
    assert accept_http(ctx,data,raw).status_code==201
    _,csrf=target_session(ctx)
    service=ImportStaging(ctx[0][2],ctx[0][0]);ctx[0][5].app.state.import_staging=service
    product=uuid4()
    with Session(ctx[0][1]) as s:
        s.add(Product(id=product,store_id=ctx[2].store_id,name='Explicit continuation product',selling_unit='cup',active=True));s.commit()
    return ctx[0],ctx[2],service,{'Origin':ORIGIN,'X-CSRF-Token':csrf},product


def test_staff_submission_owner_review_then_separate_preview_confirm_commit(staff_env):
    ctx=staff_env;staff=staff_import(ctx)
    ident=analyzed(staff);declare_context(staff,ident,{'missing_stockout':'not_provided'})
    response,profile,_=submit(staff,ident);assert response.status_code==201,response.text
    row=response.json()['data'];owner_session(ctx)
    owner=(ctx[0],ctx[2],staff[2],ctx[5],staff[4])
    approved=post(owner,f'/stores/{ctx[2].store_id}/mapping-profiles/{profile["profile_id"]}/decisions',
        dict(decision='approve_activate',proposal_revision=profile['proposal_revision'],expected_active_version=None,
            submission_id=row['submission_id'],expected_submission_version=row['version'],reason='Owner reviews pinned spec'),match=profile['lifecycle_revision'])
    assert approved.status_code==200,approved.text
    with Session(ctx[0][1]) as fresh: assert fresh.scalar(select(func.count()).select_from(SalesDaily))==0
    _,csrf=target_session(ctx);staff[3]['X-CSRF-Token']=csrf
    read=previewed(staff,ident)
    from tests.integration.test_import_classification import confirm
    from tests.integration.test_import_commit import commit,finished
    reviewed=confirm(staff,ident,read);assert reviewed.status_code==200,reviewed.text
    receipt=finished(staff,ident,commit(staff,ident,read,reviewed.json()['data']['import_revision']))
    assert receipt['outcome']=='committed'
    with Session(ctx[0][1]) as fresh:
        sales=fresh.scalars(select(SalesDaily)).all();assert len(sales)==1 and sales[0].quantity==105
        assert fresh.get(MappingSubmissionRecord,UUID(row['submission_id'])).state=='approved'
        assert fresh.scalar(select(func.count()).select_from(ImportProfileVersion))==1


def test_queue_concurrent_decisions_lost_ack_and_submission_cas(imp,monkeypatch):
    ident=analyzed(imp);declare_context(imp,ident)
    response,profile,_=submit(imp,ident);row=response.json()['data']
    path=f'/stores/{imp[1].store_id}/mapping-profiles/{profile["profile_id"]}/decisions'
    body=dict(decision='approve_activate',proposal_revision=profile['proposal_revision'],expected_active_version=None,
        submission_id=row['submission_id'],expected_submission_version='stale',reason='Owner decision')
    assert post(imp,path,body,match=profile['lifecycle_revision']).json()['error']['code']=='MAPPING_SUBMISSION_STALE'
    body['expected_submission_version']=row['version']
    with ThreadPoolExecutor(max_workers=2) as pool:
        codes=sorted(pool.map(lambda _:post(imp,path,body,match=profile['lifecycle_revision']).status_code,range(2)))
    assert codes==[200,412]
    ident=analyzed(imp);declare_context(imp,ident,{'source_system_key':'POS-UNCERTAIN'})
    response,profile,_=submit(imp,ident);row=response.json()['data'];key=str(uuid4())
    path=f'/stores/{imp[1].store_id}/mapping-profiles/{profile["profile_id"]}/decisions'
    body=dict(decision='approve_activate',proposal_revision=profile['proposal_revision'],expected_active_version=None,reason='Retained uncertain decision')
    original=Session.commit
    def uncertain(s):
        original(s);raise OperationalError('synthetic lost ACK',{},Exception('synthetic'))
    with monkeypatch.context() as patch:
        patch.setattr(Session,'commit',uncertain)
        assert post(imp,path,body,key=key,match=profile['lifecycle_revision']).status_code==503
    retained=post(imp,path,body,key=key,match=profile['lifecycle_revision']);assert retained.status_code==200,retained.text
    assert retained.json()['data']['submission']['submission_id']==row['submission_id']
    with Session(imp[0][1]) as fresh: assert fresh.scalar(select(func.count()).select_from(ImportProfileVersion))==2


def test_requests_cross_actor_store_and_delivered_target_role_reauthorization(staff_env):
    ctx=staff_env;member=prepare(ctx);row=permission_submit(ctx,member).json()['data'];owner_session(ctx)
    setup(ctx[0],'second@example.test',store=False)
    invitation,raw=create(ctx,email='second@example.test',grants=())
    result,token=ctx[0][2].login(LoginRequest(email='second@example.test',password=PASSWORD),'second-client')
    ctx[0][5].cookies.set('__Host-shelfcash_session',token,domain='backend.example.test',path='/')
    accepted=ctx[0][5].post(f'/api/v1/staff-invitations/{invitation["invitation"]["invitation_id"]}/accept',
        headers={'Origin':ORIGIN,'X-CSRF-Token':result.session.csrf_token,'Idempotency-Key':str(uuid4()),'If-Match':invitation['invitation']['version']},json={'token':raw,'accept':True})
    assert accepted.status_code==201,accepted.text
    base=f'/api/v1/stores/{ctx[2].store_id}/permission-requests'
    assert ctx[0][5].get(base).json()['data']['items']==[]
    assert ctx[0][5].get(base+'/'+row['request_id']).status_code==404
    foreign=setup(ctx[0],'foreign@example.test')
    owner_session(ctx)
    assert ctx[0][5].get(f'/api/v1/stores/{foreign.store_id}/permission-requests/{row["request_id"]}').status_code==404
    assert NotificationDispatcher(ctx[0][1],ctx[0][2].clock).dispatch()==1
    assert ctx[0][5].get('/api/v1/notifications').json()['data']['items'][0]['link']
    with Session(ctx[0][1]) as s:
        membership=s.scalar(select(StoreMembership).where(StoreMembership.user_id==ctx[2].user_id,StoreMembership.store_id==ctx[2].store_id))
        membership.role='STAFF';s.commit()
    wire=ctx[0][5].get('/api/v1/notifications').json()['data']['items'];assert len(wire)==1 and wire[0]['link'] is None


def test_current_staff_session_and_catalogue_fences(staff_env):
    ctx=staff_env;member=prepare(ctx)
    row=permission_submit(ctx,member).json()['data']
    old_staff_token=ctx[0][5].cookies.get('__Host-shelfcash_session')
    owner_session(ctx)
    path=f'/api/v1/stores/{ctx[2].store_id}/permission-requests/{row["request_id"]}/actions'
    headers={**ctx[5],'Idempotency-Key':str(uuid4()),'If-Match':'"'+row['version']+'"'}
    body=dict(action='approve',approved_permissions=['sales.read'],permission_catalog_version='old',
        expected_grants_version=row['current_grants_version'],reason='Approve supported catalogue subset')
    assert ctx[0][5].post(path,json=body,headers=headers).json()['error']['code']=='PERMISSION_CATALOG_CHANGED'
    body['permission_catalog_version']='permissions-v3'
    assert ctx[0][5].post(path,json=body,headers=headers).status_code==200
    # Reuse exactly the pre-approval session; do not log in again to refresh grants.
    ctx[0][5].cookies.set('__Host-shelfcash_session',old_staff_token,domain='backend.example.test',path='/')
    current=ctx[0][5].get(f'/api/v1/stores/{ctx[2].store_id}').json()['data']['membership']
    assert {'menu.read','sales.read'} <= set(current['effective_permissions'])


def test_queue_snapshots_evidence_cursors_and_foreign_targets(imp):
    ident=analyzed(imp);declare_context(imp,ident)
    response,profile,_=submit(imp,ident);row=response.json()['data']
    second=analyzed(imp);declare_context(imp,second,{'source_system_key':'POS-SECOND'})
    assert submit(imp,second)[0].status_code==201
    base=f'/api/v1/stores/{imp[1].store_id}/mapping-submissions'
    first=imp[0][5].get(base+'?limit=1').json();cursor=first['meta']['pagination']['next_cursor'];assert cursor
    assert imp[0][5].get(base,params={'limit':2,'cursor':cursor}).status_code==422
    detail=imp[0][5].get(base+'/'+row['submission_id']+'?evidence_limit=2').json()['data']
    evidence_cursor=detail['evidence']['next_cursor'];assert evidence_cursor
    next_page=imp[0][5].get(base+'/'+row['submission_id'],params={'evidence_limit':2,'evidence_cursor':evidence_cursor})
    assert next_page.status_code==200,next_page.text
    declare_context(imp,ident,{'source_system_key':'POS-EDITED'})
    assert imp[0][5].get(base,params={'limit':1,'cursor':cursor}).status_code==409
    assert imp[0][5].get(base+'/'+row['submission_id'],params={'evidence_limit':2,'evidence_cursor':evidence_cursor}).status_code==409
    foreign=setup(imp[0],'foreign@example.test')
    assert imp[0][5].get(f'/api/v1/stores/{foreign.store_id}/mapping-submissions/{row["submission_id"]}').status_code==404
    assert imp[0][5].get(base,params={'file_id':str(uuid4())}).status_code==404


def test_submit_intent_rollback_and_reject_producer(imp,monkeypatch):
    ident=analyzed(imp);declare_context(imp,ident);key=str(uuid4())
    from app.repositories import notifications
    original=notifications.enqueue
    def fail(s,event):
        original(s,event);raise IntegrityError('synthetic',{},Exception('synthetic'))
    with monkeypatch.context() as patch:
        patch.setattr(notifications,'enqueue',fail)
        assert submit(imp,ident,key=key)[0].status_code==503
    with Session(imp[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(MappingSubmissionRecord))==0
    response,profile,_=submit(imp,ident,key=key);assert response.status_code==201,response.text
    row=response.json()['data']
    result=post(imp,f'/stores/{imp[1].store_id}/mapping-profiles/{profile["profile_id"]}/decisions',
        dict(decision='reject',proposal_revision=profile['proposal_revision'],reason='Explicit rejection',
            submission_id=row['submission_id'],expected_submission_version=row['version']),match=profile['lifecycle_revision'])
    assert result.status_code==200,result.text
    assert result.json()['data']['submission']['state']=='rejected'
    assert NotificationDispatcher(imp[0][1],imp[0][2].clock).dispatch()==2
    with Session(imp[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(ImportProfileVersion))==0
        assert fresh.scalar(select(func.count()).select_from(SalesDaily))==0
        from app.models.notifications import NotificationIntent
        assert sorted(fresh.scalars(select(NotificationIntent.event_type)))==['mapping_submission.rejected','mapping_submission.submitted']


def test_n5_without_queue_fields_preserves_original_receipt_fingerprint(imp):
    ident=analyzed(imp);declare_context(imp,ident)
    profile=summary(imp,ident)['profile_proposals'][0];key=str(uuid4())
    body=dict(decision='approve_activate',proposal_revision=profile['proposal_revision'],expected_active_version=None,reason='Original N5 request shape')
    result=post(imp,f'/stores/{imp[1].store_id}/mapping-profiles/{profile["profile_id"]}/decisions',
        body,key=key,match=profile['lifecycle_revision'])
    assert result.status_code==200,result.text
    from app.infrastructure.auth_crypto import digest
    import json
    expected=digest(json.dumps([body,profile['lifecycle_revision']],sort_keys=True,separators=(',',':')))
    with Session(imp[0][1]) as fresh:
        receipt=fresh.get(ImportReceipt,(imp[1].user_id,imp[1].store_id,'POST:profiles/'+profile['profile_id']+'/decisions',digest(key)))
        assert receipt.request_digest==expected


def test_terminal_queue_snapshot_tracks_batch_revision_and_bounded_evidence(imp):
    base=f'/api/v1/stores/{imp[1].store_id}/mapping-submissions'
    rows=[]
    for source in ('POS-HISTORY-A','POS-HISTORY-B'):
        ident=analyzed(imp);declare_context(imp,ident,{'source_system_key':source})
        response,profile,revision=submit(imp,ident);row=response.json()['data'];rows.append((ident,row))
        assert post(imp,f'/imports/{ident}/mapping-submissions',dict(action='withdraw',submission_id=row['submission_id'],
            expected_submission_version=row['version'],reason='Explicit history'),match=revision).status_code==200
    first=imp[0][5].get(base,params={'state':'withdrawn','limit':1}).json()
    cursor=first['meta']['pagination']['next_cursor'];assert cursor
    ident,row=rows[0]
    detail=imp[0][5].get(base+'/'+row['submission_id'],params={'evidence_limit':2}).json()['data']
    next_cursor=detail['evidence']['next_cursor'];assert next_cursor
    seen=list(detail['evidence']['cells'])
    while next_cursor:
        page=imp[0][5].get(base+'/'+row['submission_id'],params={'evidence_limit':2,'evidence_cursor':next_cursor}).json()['data']['evidence']
        assert len(page['cells'])<=2
        seen.extend(page['cells']);next_cursor=page['next_cursor']
    assert len(seen)==detail['evidence']['total_count']==5
    with Session(imp[0][1]) as fresh:
        retained=fresh.get(MappingSubmissionRecord,UUID(row['submission_id']))
        assert isinstance(retained.evidence,dict) and 'cells' not in retained.evidence
        assert retained.evidence['total_count']==5
        batch=fresh.get(ImportBatch,UUID(ident));batch.revision=str(uuid4());fresh.commit()
    assert imp[0][5].get(base,params={'state':'withdrawn','limit':1,'cursor':cursor}).status_code==409


def test_permission_request_facts_audit_and_terminal_retention(staff_env):
    ctx=staff_env;member=prepare(ctx);row=permission_submit(ctx,member).json()['data']
    path=f'/api/v1/stores/{ctx[2].store_id}/permission-requests/{row["request_id"]}'
    assert ctx[0][5].get(path).headers['Cache-Control']=='private, no-store'
    assert ctx[0][5].request('GET',path,content='{}').status_code==400
    with Session(ctx[0][1]) as s:
        retained=s.get(PermissionRequestRecord,UUID(row['request_id']))
        retained.facts={**retained.facts,'reason':'Overwritten fact'}
        with pytest.raises(DBAPIError): s.commit()
        s.rollback()
        audit=s.scalar(select(PermissionRequestAudit))
        audit.record={**audit.record,'reason':'Overwritten audit'}
        with pytest.raises(DBAPIError): s.commit()
        s.rollback()
        s.delete(s.get(PermissionRequestRecord,UUID(row['request_id'])))
        with pytest.raises(DBAPIError): s.commit()
    from tests.integration.test_permission_requests import approve
    assert approve(ctx,row).status_code==200
    with Session(ctx[0][1]) as s:
        retained=s.get(PermissionRequestRecord,UUID(row['request_id']));retained.state='pending'
        with pytest.raises(DBAPIError): s.commit()
    with Session(ctx[0][1]) as fresh:
        assert fresh.get(PermissionRequestRecord,UUID(row['request_id'])).state=='approved'
        assert fresh.scalar(select(func.count()).select_from(PermissionRequestAudit))==2


def test_mapping_pin_terminal_and_migration_retention(imp):
    ident=analyzed(imp);declare_context(imp,ident)
    response,profile,revision=submit(imp,ident);row=response.json()['data']
    path=f'/api/v1/stores/{imp[1].store_id}/mapping-submissions/{row["submission_id"]}'
    assert imp[0][5].get(path).headers['Cache-Control']=='private, no-store'
    assert imp[0][5].request('GET',path,content='{}').status_code==400
    with Session(imp[0][1]) as s:
        retained=s.get(MappingSubmissionRecord,UUID(row['submission_id']))
        retained.spec={**retained.spec,'schema':'ingredients'}
        with pytest.raises(DBAPIError): s.commit()
        s.rollback()
        retained=s.get(MappingSubmissionRecord,UUID(row['submission_id']));retained.evidence={'total_count':0}
        with pytest.raises(DBAPIError): s.commit()
    assert post(imp,f'/imports/{ident}/mapping-submissions',dict(action='withdraw',submission_id=row['submission_id'],
        expected_submission_version=row['version'],reason='Explicit terminal retention'),match=revision).status_code==200
    with Session(imp[0][1]) as s:
        retained=s.get(MappingSubmissionRecord,UUID(row['submission_id']));retained.state='submitted'
        with pytest.raises(DBAPIError): s.commit()
    from alembic import command
    from scripts.dev import migration_config
    with pytest.raises(RuntimeError,match='retention'):
        command.downgrade(migration_config(),'0025_notifications_foundation')
    with Session(imp[0][1]) as fresh:
        from sqlalchemy import text
        assert fresh.scalar(text('SELECT version_num FROM alembic_version'))=='0026_collaboration_requests'
        assert fresh.get(MappingSubmissionRecord,UUID(row['submission_id'])).state=='withdrawn'
