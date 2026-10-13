"""PLAN14 real HTTP/PostgreSQL, guarded test DB, fresh committed state."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4
import pytest
from sqlalchemy import select,func,event
from sqlalchemy.orm import Session
from tests.integration.test_auth_public import env,setup,login
from app.application.use_cases.planning_configuration import PlanningConfigurationWrites
from app.models import Product,StoreMembership
from app.models.auth import MembershipGrant
from app.models.planning_configuration import (SavedRequirement,PlanningBudget,PlanningDefault,
    PlanningConfigurationEvent,PlanningConfigurationReceipt,PlanningConfigurationRevision)


@pytest.fixture
def config(env):
    owner=setup(env)
    wire=login(env).json()['data']
    env[5].app.state.planning_configuration=PlanningConfigurationWrites(env[2])
    product=uuid4()
    with Session(env[1]) as s:
        s.add(Product(id=product,store_id=owner.store_id,name='Synthetic tea',selling_unit='cup',active=True))
        s.add(PlanningDefault(store_id=owner.store_id,version='default-1',updated_at=env[4][0]-timedelta(days=1),
            requirements_json={'budget_limit':None,'paths':[{'path':'BASE','min_fill_rate_percent':'95','product_overrides':[]}]}))
        s.commit()
    headers={'Origin':'https://fe.example.test','X-CSRF-Token':wire['session']['csrf_token']}
    return env,owner,product,headers


def base(c):
    return f'/api/v1/stores/{c[1].store_id}'


def full(**changes):
    return {**dict(name='Save without history or recipe',requirements=dict(paths=[dict(path='BASE',min_fill_rate_percent='95',product_overrides=[])],budget_limit=None)),**changes}


def save(c,body=None,headers=None):
    return c[0][5].post(base(c)+'/planning-requirements',json=body or full(),headers=headers or {**c[3],'Idempotency-Key':str(uuid4())})


def cap(c,amount='100',**conditions):
    return c[0][5].put(base(c)+'/planning-budget',json={'amount':amount},headers={**c[3],'Idempotency-Key':str(uuid4()),**conditions})


def test_save_without_execution_prerequisites_null_cap_and_exact_replay(config):
    c=config;headers={**c[3],'Idempotency-Key':str(uuid4())}
    response=save(c,headers=headers);assert response.status_code==201,response.text
    value=response.json()['data'];assert value['validation']==dict(status='unknown',reason_codes=['BUDGET_CEILING_UNKNOWN'])
    assert value['requirements']['budget_limit'] is None and value['default_reference'] is None
    assert save(c,headers=headers).json()['data']==value
    assert save(c,{**full(),'name':'different'},headers).status_code==409
    with Session(c[0][1]) as s:
        assert s.scalar(select(func.count()).select_from(SavedRequirement))==1
        assert s.scalar(select(func.count()).select_from(PlanningConfigurationEvent))==1
        assert s.scalar(select(func.count()).select_from(PlanningConfigurationReceipt))==1
        assert s.scalar(select(func.count()).select_from(PlanningConfigurationRevision))==1


def test_malformed_and_inapplicable_conditional_headers_are_400(config):
    c=config
    for extra in ({'Idempotency-Key':'x'*129},{'If-Match':'"not-applicable"'},{'If-None-Match':'*'}):
        response=save(c,headers={**c[3],'Idempotency-Key':str(uuid4()),**extra})
        assert response.status_code==400,response.text
        assert response.json()['meta']=={}
    value=save(c).json()['data']
    response=c[0][5].put(base(c)+'/planning-requirements/'+value['saved_requirement_id'],json={'state':'archived'},headers={
        **c[3],'Idempotency-Key':str(uuid4()),'If-Match':'"'+value['version']+'"','If-None-Match':'*'})
    assert response.status_code==400,response.text


def test_default_inheritance_stale_and_full_custom_ignores_stale(config):
    c=config
    inherited=dict(name='Inherit',requirements={'paths':[{'path':'BASE'}]})
    assert save(c,inherited).status_code==422
    assert save(c,{**inherited,'default_requirements_version':'stale'}).status_code==409
    value=save(c,{**inherited,'default_requirements_version':'default-1'})
    assert value.status_code==201,value.text
    assert value.json()['data']['requirements']['paths'][0]['min_fill_rate_percent']=='95'
    assert value.json()['data']['default_reference']['version']=='default-1'
    assert save(c,full(default_requirements_version='stale')).status_code==201
    assert save(c,dict(name='LOW',requirements={'paths':[{'path':'LOW'}]},default_requirements_version='default-1')).status_code==422


def test_budget_create_only_cas_zero_noop_and_saved_invalidity(config):
    c=config
    assert cap(c).status_code==428
    first=cap(c,**{'If-None-Match':'*'});assert first.status_code==201,first.text
    value=first.json()['data']['budget_ceiling']
    assert cap(c,**{'If-None-Match':'*'}).status_code==412
    body=full();body['requirements']['budget_limit']='90'
    saved=save(c,body).json()['data'];path=base(c)+'/planning-requirements/'+saved['saved_requirement_id']
    same=cap(c,'100.00',**{'If-Match':'"'+value['version']+'"'})
    assert same.json()['data']['budget_ceiling']==value
    lowered=cap(c,'0',**{'If-Match':'"'+value['version']+'"'});assert lowered.status_code==200,lowered.text
    current=c[0][5].get(path).json()['data']
    assert current['requirements']['budget_limit']=='90' and current['updated_at']==saved['updated_at']
    assert current['validation']['status']=='invalid'
    assert cap(c,**{'If-Match':'"'+value['version']+'"'}).status_code==412


def test_save_override_scope_inactive_and_private_budget(config):
    c=config
    body=full();body['requirements']['paths'][0]['product_overrides']=[dict(product_id=str(uuid4()),min_fill_rate_percent='0')]
    assert save(c,body).status_code==422
    body['requirements']['paths'][0]['product_overrides'][0]['product_id']=str(c[2])
    with Session(c[0][1]) as s:s.get(Product,c[2]).active=False;s.commit()
    assert save(c,body).status_code==422
    body=full();body['requirements']['budget_limit']='0'
    assert save(c,body).status_code==422
    assert cap(c,'0',**{'If-None-Match':'*'}).status_code==201
    assert save(c,body).status_code==201


def test_archive_noop_replay_after_change_and_creator_immutable(config):
    c=config;saved=save(c).json()['data'];path=base(c)+'/planning-requirements/'+saved['saved_requirement_id']
    headers={**c[3],'Idempotency-Key':str(uuid4()),'If-Match':'"'+saved['version']+'"'}
    same=c[0][5].put(path,json={'state':'active',**full()},headers=headers)
    assert same.json()['data']==saved
    archived=c[0][5].put(path,json={'state':'archived'},headers={**headers,'Idempotency-Key':str(uuid4())})
    assert archived.status_code==200,archived.text
    value=archived.json()['data'];assert value['validation']['reason_codes']==['SAVED_REQUIREMENTS_ARCHIVED']
    assert value['created_by_user_id']==saved['created_by_user_id']
    assert c[0][5].put(path,json={'state':'active',**full()},headers=headers).json()['data']==saved
    fresh={**headers,'Idempotency-Key':str(uuid4()),'If-Match':'"'+value['version']+'"'}
    assert c[0][5].put(path,json={'state':'archived'},headers=fresh).json()['data']==value
    assert c[0][5].put(path,json={'state':'active',**full()},headers={**fresh,'Idempotency-Key':str(uuid4())}).status_code==409


def test_real_concurrent_budget_cas_single_winner(config):
    c=config;first=cap(c,**{'If-None-Match':'*'}).json()['data']['budget_ceiling']
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(lambda amount:cap(c,amount,**{'If-Match':'"'+first['version']+'"'}),('50','60')))
    assert sorted(r.status_code for r in responses)==[200,412]
    with Session(c[0][1]) as s:
        assert s.get(PlanningBudget,c[1].store_id).amount in ('50','60')
        assert s.scalar(select(func.count()).select_from(PlanningConfigurationEvent))==2


def test_actual_commit_ack_loss_reconciles_and_write_failure_rolls_back(config,monkeypatch):
    c=config;original=Session.commit;lost=[False]
    def commit(s):
        has_save=any(isinstance(x,SavedRequirement) for x in s.identity_map.values())
        original(s)
        if has_save and not lost[0]:
            lost[0]=True;raise OSError('Lost ack')
    monkeypatch.setattr(Session,'commit',commit)
    response=save(c);assert response.status_code==201,response.text
    assert lost[0]
    monkeypatch.setattr(Session,'commit',original)
    def fail(s,context,instances):
        if any(isinstance(x,PlanningConfigurationEvent) for x in s.new):
            raise RuntimeError('storage failure')
    event.listen(Session,'before_flush',fail)
    try:
        assert save(c,full(name='must rollback')).status_code==503
    finally:event.remove(Session,'before_flush',fail)
    with Session(c[0][1]) as s:
        assert s.scalar(select(func.count()).select_from(SavedRequirement))==1
        assert s.scalar(select(func.count()).select_from(PlanningConfigurationEvent))==1


def test_staff_read_other_manage_own_owner_manage_all_current_revoke(config):
    c=config;owner_save=save(c).json()['data']
    staff=setup(c[0],'staff@example.test',store=False)
    with Session(c[0][1]) as s:
        member=StoreMembership(id=uuid4(),store_id=c[1].store_id,user_id=staff.user_id,role='STAFF',active=True)
        s.add(member);s.flush()
        for grant in ('planning.requirements.read','planning.requirements.create','planning.requirements.manage','budget.read'):
            s.add(MembershipGrant(membership_id=member.id,permission=grant))
        mid=member.id;s.commit()
    wire=login(c[0],'staff@example.test').json()['data']
    c=(c[0],c[1],c[2],{**c[3],'X-CSRF-Token':wire['session']['csrf_token']})
    path=base(c)+'/planning-requirements/'+owner_save['saved_requirement_id']
    assert c[0][5].get(path).status_code==200
    assert c[0][5].put(path,json={'state':'archived'},headers={**c[3],'If-Match':'"'+owner_save['version']+'"','Idempotency-Key':str(uuid4())}).status_code==403
    own=save(c);assert own.status_code==201,own.text
    val=own.json()['data'];assert val['created_by_user_id']==str(staff.user_id)
    ownpath=base(c)+'/planning-requirements/'+val['saved_requirement_id']
    headers={**c[3],'If-Match':'"'+val['version']+'"','Idempotency-Key':str(uuid4())}
    assert c[0][5].put(ownpath,json={'state':'archived'},headers=headers).status_code==200
    with Session(c[0][1]) as s:s.get(StoreMembership,mid).active=False;s.commit()
    assert c[0][5].put(ownpath,json={'state':'archived'},headers=headers).status_code==404


def test_transport_invalid_headers_body_limit_and_unknown_fields(config):
    c=config
    assert save(c,headers={**c[3],'Idempotency-Key':'bad'}).status_code==400
    assert cap(c,**{'If-Match':'bad','If-None-Match':'*'}).status_code==400
    assert save(c,{**full(),'creator':str(uuid4())}).json()['error']['details']['field_errors'][0]['code']=='UNKNOWN_FIELD'
    r=c[0][5].post(base(c)+'/planning-requirements',content=b' '*65537,headers={**c[3],'Idempotency-Key':str(uuid4()),'Content-Type':'application/json'})
    assert r.status_code==413 and r.json()['error']['code']=='REQUEST_TOO_LARGE'
