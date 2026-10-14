"""HTTP review queue fences with retained PostgreSQL evidence."""
from uuid import UUID,uuid4
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from tests.integration.test_import_staging import imp,env,analyzed,post
from tests.integration.test_import_rule_review import summary,declare_context
from app.models.import_staging import ImportBatch,ImportProfileVersion
from app.models.collaboration import MappingSubmissionRecord
from app.models.notifications import NotificationIntent
from app.models import SalesDaily
import pytest
from sqlalchemy.exc import IntegrityError
from tests.integration.test_staff_public import staff_env,create,accept_http,target_session,owner_session
from tests.integration.test_auth_public import ORIGIN


def submit(imp,ident,*,key=None):
    proposed=summary(imp,ident); profile=proposed['profile_proposals'][0]
    with Session(imp[0][1]) as s: revision=s.get(ImportBatch,UUID(ident)).revision
    r=post(imp,f'/imports/{ident}/mapping-submissions',dict(action='submit',profile_id=profile['profile_id'],
        proposal_revision=profile['proposal_revision'],mapping_revision=proposed['mapping_revision'],reason='Review synthetic full spec'),match=revision,key=key)
    return r,profile,revision


def test_queue_pins_n5_and_replay_without_business_commit(imp):
    ident=analyzed(imp); declare_context(imp,ident)
    key=str(uuid4()); response,profile,revision=submit(imp,ident,key=key)
    assert response.status_code==201,response.text
    row=response.json()['data']; assert response.headers['etag']=='"'+revision+'"'
    assert submit(imp,ident,key=key)[0].json()['data']==row
    assert submit(imp,ident)[0].json()['error']['code']=='MAPPING_ALREADY_SUBMITTED'
    base=f'/api/v1/stores/{imp[1].store_id}/mapping-submissions'
    assert imp[0][5].get(base).json()['data']['items'][0]==row
    detail=imp[0][5].get(base+'/'+row['submission_id']+'?evidence_limit=2')
    assert detail.status_code==200,detail.text
    pinned=detail.json()['data']; assert len(pinned['evidence']['cells'])==2 and pinned['evidence']['next_cursor']
    body=dict(decision='approve_activate',proposal_revision=profile['proposal_revision'],expected_active_version=None,
        reason='Explicit grouped review',submission_id=row['submission_id'],expected_submission_version=row['version'])
    decision_key=str(uuid4()); path=f'/stores/{imp[1].store_id}/mapping-profiles/{profile["profile_id"]}/decisions'
    decided=post(imp,path,body,match=profile['lifecycle_revision'],key=decision_key)
    assert decided.status_code==200,decided.text
    result=decided.json()['data']; assert result['submission']['state']=='approved' and result['notification_delivery']['status']=='pending'
    assert post(imp,path,body,match=profile['lifecycle_revision'],key=decision_key).json()['data']==result
    with Session(imp[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(ImportProfileVersion))==1
        assert fresh.scalar(select(func.count()).select_from(SalesDaily))==0
        assert fresh.get(MappingSubmissionRecord,UUID(row['submission_id'])).spec==pinned['spec']
        assert fresh.scalar(select(func.count()).select_from(NotificationIntent))==2
    assert imp[0][5].get(base).json()['data']['items']==[]
    assert summary(imp,ident)['can_preview']
    assert imp[0][5].get(base+'/'+row['submission_id']).json()['data']['spec']==pinned['spec']


def test_mapping_edit_atomic_stale_and_immutable_pin(imp):
    ident=analyzed(imp); declare_context(imp,ident)
    response,profile,_=submit(imp,ident); assert response.status_code==201,response.text
    row=response.json()['data']; base=f'/api/v1/stores/{imp[1].store_id}/mapping-submissions'
    detail=imp[0][5].get(base+'/'+row['submission_id']).json()['data']
    declare_context(imp,ident,dict(source_system_key='POS-CHANGED'))
    changed=imp[0][5].get(base+'/'+row['submission_id']).json()['data']
    assert changed['submission']['state']=='stale' and changed['spec']==detail['spec']
    with Session(imp[0][1]) as fresh: assert fresh.get(MappingSubmissionRecord,UUID(row['submission_id'])).state=='stale'
    current=summary(imp,ident)['profile_proposals'][0]
    decision=post(imp,f'/stores/{imp[1].store_id}/mapping-profiles/{profile["profile_id"]}/decisions',
        dict(decision='approve_activate',proposal_revision=current['proposal_revision'],expected_active_version=None,
             submission_id=row['submission_id'],expected_submission_version=row['version'],reason='Stale review'),match=current['lifecycle_revision'])
    assert decision.status_code==409
    freshrow,_,_=submit(imp,ident); assert freshrow.status_code==201,freshrow.text
    assert freshrow.json()['data']['submission_id']!=row['submission_id']


def test_withdraw_and_retirement_history(imp):
    ident=analyzed(imp); declare_context(imp,ident)
    response,profile,revision=submit(imp,ident); row=response.json()['data']
    withdrawn=post(imp,f'/imports/{ident}/mapping-submissions',dict(action='withdraw',submission_id=row['submission_id'],
        expected_submission_version=row['version'],reason='Withdraw explicit task'),match=revision)
    assert withdrawn.status_code==200,withdrawn.text
    assert withdrawn.headers['etag']=='"'+revision+'"' and withdrawn.json()['data']['state']=='withdrawn'
    response,profile,revision=submit(imp,ident); row=response.json()['data']
    path=f'/stores/{imp[1].store_id}/mapping-profiles/{profile["profile_id"]}/decisions'
    approved=post(imp,path,dict(decision='approve_activate',proposal_revision=profile['proposal_revision'],expected_active_version=None,reason='Direct queued approval'),match=profile['lifecycle_revision']).json()['data']
    assert approved['submission']['submission_id']==row['submission_id']
    retired=post(imp,path,dict(decision='retire',active_version=approved['active_version'],reason='Explicit retire'),match=approved['lifecycle_revision'])
    assert retired.status_code==200,retired.text
    detail=imp[0][5].get(f'/api/v1/stores/{imp[1].store_id}/mapping-submissions/{row["submission_id"]}').json()['data']['submission']
    assert detail['state']=='approved' and detail['current_profile']['reviewed_version_retired'] and detail['allowed_actions']==[]


def test_n5_notification_failure_rollback_then_retry_and_dispatch_recovery(imp,monkeypatch):
    ident=analyzed(imp); declare_context(imp,ident)
    response,profile,_=submit(imp,ident); row=response.json()['data']
    from app.repositories import notifications
    original=notifications.enqueue
    def fail(s,event):
        original(s,event); raise IntegrityError('synthetic',{},Exception('synthetic'))
    path=f'/stores/{imp[1].store_id}/mapping-profiles/{profile["profile_id"]}/decisions'; key=str(uuid4())
    body=dict(decision='approve_activate',proposal_revision=profile['proposal_revision'],expected_active_version=None,reason='Atomic decision')
    with monkeypatch.context() as patch:
        patch.setattr(notifications,'enqueue',fail)
        assert post(imp,path,body,key=key,match=profile['lifecycle_revision']).status_code==503
    with Session(imp[0][1]) as fresh:
        assert fresh.get(MappingSubmissionRecord,UUID(row['submission_id'])).state=='submitted'
        assert fresh.scalar(select(func.count()).select_from(ImportProfileVersion))==0
    assert post(imp,path,body,key=key,match=profile['lifecycle_revision']).status_code==200
    from app.application.use_cases.notification_delivery import NotificationDispatcher
    assert NotificationDispatcher(imp[0][1],imp[0][2].clock).dispatch()==2
    assert NotificationDispatcher(imp[0][1],imp[0][2].clock).dispatch()==0
    inbox=imp[0][5].get('/api/v1/notifications').json()['data']['items']
    assert len(inbox)==2 and all(i['link'] for i in inbox)
    assert 'Profile đã được duyệt; mở batch để kiểm tra và tiếp tục nhập.' in [i['body'] for i in inbox]
    with Session(imp[0][1]) as fresh: assert fresh.scalar(select(func.count()).select_from(SalesDaily))==0


def test_staff_own_queue_sensitive_revoke_and_notification_target_denial(staff_env):
    ctx=staff_env
    from app.application.use_cases.import_staging import ImportStaging
    from app.domain.permissions import PERMISSIONS
    from app.models import Product
    data,raw=create(ctx,grants=tuple(sorted(PERMISSIONS)))
    assert accept_http(ctx,data,raw).status_code==201
    _,csrf=target_session(ctx); service=ImportStaging(ctx[0][2],ctx[0][0]); ctx[0][5].app.state.import_staging=service
    product=uuid4()
    with Session(ctx[0][1]) as fresh:
        fresh.add(Product(id=product,store_id=ctx[2].store_id,name='Explicit synthetic sales product',selling_unit='cup',active=True));fresh.commit()
    staff=(ctx[0],ctx[2],service,{'Origin':ORIGIN,'X-CSRF-Token':csrf},product)
    ident=analyzed(staff);declare_context(staff,ident)
    response,profile,_=submit(staff,ident);assert response.status_code==201,response.text
    row=response.json()['data'];base=f'/api/v1/stores/{ctx[2].store_id}/mapping-submissions'
    owner_session(ctx)
    assert ctx[0][5].get(base).json()['data']['items'][0]['submission_id']==row['submission_id']
    owner=(ctx[0],ctx[2],service,ctx[5],product)
    result=post(owner,f'/stores/{ctx[2].store_id}/mapping-profiles/{profile["profile_id"]}/decisions',
        dict(decision='approve_activate',proposal_revision=profile['proposal_revision'],expected_active_version=None,reason='Owner approves Staff spec'),match=profile['lifecycle_revision'])
    assert result.status_code==200,result.text
    from app.application.use_cases.notification_delivery import NotificationDispatcher
    assert NotificationDispatcher(ctx[0][1],ctx[0][2].clock).dispatch()==2
    _,csrf=target_session(ctx)
    own=ctx[0][5].get('/api/v1/notifications').json()['data']['items'];assert len(own)==1 and own[0]['link']
    notification=own[0]
    assert ctx[0][5].patch('/api/v1/notifications/'+notification['notification_id'],json={'read':True},
        headers={**staff[3],'X-CSRF-Token':csrf,'Idempotency-Key':str(uuid4()),'If-Match':'"'+notification['version']+'"'}).status_code==200
    assert ctx[0][5].get(base).json()['data']['items'][0]['state']=='approved'
    owner_session(ctx);member=ctx[1].memberships(ctx[4],ctx[2].store_id)[0].items[0]
    from app.application.contracts.staff import GrantsRequest
    ctx[1].replace(ctx[4],ctx[2].store_id,member.membership_id,GrantsRequest(grants=tuple(sorted(PERMISSIONS-{'sales.read'})),reason='Remove source access'),str(uuid4()),member.version,ctx[5]['X-CSRF-Token'],'test')
    target_session(ctx)
    assert ctx[0][5].get(base).status_code==403
    assert ctx[0][5].get(base+'/'+row['submission_id']).status_code==403
    assert ctx[0][5].get('/api/v1/notifications').json()['data']['items'][0]['link'] is None
    with Session(ctx[0][1]) as fresh: assert fresh.scalar(select(func.count()).select_from(SalesDaily))==0


def test_changes_requested_and_direct_n5_resolve_live_submission(imp):
    ident=analyzed(imp); declare_context(imp,ident)
    response,profile,_=submit(imp,ident); assert response.status_code==201,response.text
    row=response.json()['data']
    result=post(imp,f'/stores/{imp[1].store_id}/mapping-profiles/{profile["profile_id"]}/decisions',
        dict(decision='request_changes',proposal_revision=profile['proposal_revision'],reason='Clarify explicit source'),match=profile['lifecycle_revision'])
    assert result.status_code==200,result.text
    assert result.json()['data']['submission']['submission_id']==row['submission_id']
    assert result.json()['data']['submission']['state']=='changes_requested'
    assert result.json()['data']['active_version'] is None
    with Session(imp[0][1]) as fresh:
        assert fresh.scalar(select(func.count()).select_from(ImportProfileVersion))==0
        assert fresh.scalar(select(func.count()).select_from(SalesDaily))==0
