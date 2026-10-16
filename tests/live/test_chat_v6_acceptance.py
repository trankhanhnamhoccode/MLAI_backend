"""Opt-in only: existing real AS03 path, synthetic facts, independent acceptance budget."""
import json
import os
from uuid import uuid4
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.integration.test_assistant_summary import assistant
from tests.integration.test_auth_public import env
from tests.live import test_chat_l32_live as original
from scripts import conversational_v6_acceptance as batch
from app.models import Store,StoreMembership
from app.models.auth import MembershipGrant
from app.application.use_cases.planning_public import READ_PERMISSIONS

pytestmark=pytest.mark.skipif(os.environ.get('SHELFCASH_CHAT_V6_ACCEPTANCE')!=batch.GROUP,reason='Explicit paid V6 acceptance opt-in required')


def audit_authority(state,record,path,headers,request,transport):
    before=len(transport.attempts);client=state[5];results={}
    with Session(state[1]) as s:
        member=s.scalar(select(StoreMembership).where(StoreMembership.store_id==record.store_id))
        original_role=member.role;member.role='STAFF';mid=member.id
        for right in READ_PERMISSIONS:s.add(MembershipGrant(membership_id=mid,permission=right))
        s.commit()
    try:
        for right in READ_PERMISSIONS:
            with Session(state[1]) as s:
                grant=s.scalar(select(MembershipGrant).where(MembershipGrant.membership_id==mid,MembershipGrant.permission==right))
                s.delete(grant);s.commit()
            results[right]={'retained_replay_status':client.post(path,headers=headers,json=request).status_code,
                'new_key_status':client.post(path,headers={**headers,'Idempotency-Key':str(uuid4())},json=request).status_code}
            assert set(results[right].values())=={403}
            with Session(state[1]) as s:s.add(MembershipGrant(membership_id=mid,permission=right));s.commit()
        with Session(state[1]) as s:
            member=s.get(StoreMembership,mid);member.active=False;s.commit()
        results['store_membership_inactive_status']=client.post(path,headers=headers,json=request).status_code
        assert results['store_membership_inactive_status']==404
        with Session(state[1]) as s:
            other=Store(id=uuid4(),name='Synthetic unrelated Store',timezone='UTC',currency='VND',active=True)
            s.add(other);s.flush()
            member=s.get(StoreMembership,mid);member.active=True;member.store_id=other.id;s.commit()
        results['other_store_membership_status']=client.post(path,headers=headers,json=request).status_code
        assert results['other_store_membership_status']==404
    finally:
        with Session(state[1]) as s:
            member=s.get(StoreMembership,mid);member.role=original_role;member.active=True;member.store_id=record.store_id
            for grant in s.scalars(select(MembershipGrant).where(MembershipGrant.membership_id==mid)):s.delete(grant)
            s.commit()
    results['additional_completions']=len(transport.attempts)-before
    assert results['additional_completions']==0
    return results


@pytest.mark.parametrize('case',original.CASES)
def test_v6_acceptance_as03(assistant,case,monkeypatch):
    monkeypatch.setattr(original,'ROOT',batch.ROOT)
    monkeypatch.setattr(original,'reserve',batch.reserve)
    monkeypatch.setattr(original,'reservations',batch.reservations)
    monkeypatch.setattr(original,'MAX_ATTEMPTS',batch.MAX_ATTEMPTS)
    parent=original.Transport
    class Transport(parent):
        def open(self,request,timeout):
            assert not (batch.ROOT/'STOP-429.json').exists(),'HTTP429 stops batch'
            try:return super().open(request,timeout)
            finally:
                if self.rate_limited:
                    path=batch.ROOT/'STOP-429.json'
                    if not path.exists():
                        with path.open('x',encoding='utf8') as out:json.dump(dict(group=batch.GROUP,http_status=429,usage='UNKNOWN unless retained',action='STOP_NO_RETRY'),out)
    monkeypatch.setattr(original,'Transport',Transport)
    original.run_case(assistant,case,monkeypatch,audit_final=audit_authority)
