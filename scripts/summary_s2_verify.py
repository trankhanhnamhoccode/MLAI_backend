"""Final-source mock faults/cold reads on owned S2 state, without DB reset or paid calls."""
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID,uuid4
from concurrent.futures import ThreadPoolExecutor
from threading import Event

from scripts.summary_s2_live import ROOT,settings,prepare,ledger,write,fingerprint


def main():
    from tests.integration.test_auth_public import env,setup,login
    from tests.integration.test_assistant_summary import test_dead_process_explicit_replay_never_reissues_provider_attempt
    from tests.integration.test_summary_narrative import FakeNarrative
    from app.application.contracts.summary_narrative import CompactNarrative
    from app.infrastructure.plan_summary_provider import PresentationResult
    from app.application.contracts.plan_summary import SummaryRequest,SummaryProfile
    from app.application.use_cases.plan_summary import decode_summary
    from app.models import StoreMembership
    from app.models.auth import MembershipGrant
    from app.models.plan_summary import PlanSummaryGeneration
    from app.application.use_cases.planning_public import READ_PERMISSIONS
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    before=ledger()
    gen=env.__wrapped__(settings());state=next(gen)
    try:
        service,freeze,token,csrf,origin=prepare(state)
        case=freeze['matrix']['A'];run=UUID(case['run_id']);request=SummaryRequest(**case['request'])
        path=f'/api/v1/procurement-plans/{run}/assistant/summary'
        def profile(label):
            service.profile=SummaryProfile(enabled=True,model='synthetic-s2-'+label+'-'+str(uuid4()),max_tokens=1200,version='summary_profile/4')
        class Fake(FakeNarrative):
            def present(self,payload,profile):
                body=json.loads(payload)
                # Build locally issued refs via the actual selected evidence.
                e=service._evidence(token,run,request)
                from app.application.summary_narrative import communication_plan
                compact=CompactNarrative(clauses=tuple(dict(fact_id=f.fact_id,text=f.surfaces[-1]) for f in communication_plan(e,request)))
                self.calls+=1
                from app.application.contracts.plan_summary import SummaryDiagnostics
                return PresentationResult(None,SummaryDiagnostics(disposition='ACCEPTED',reason='NONE',requested_model=profile.model,
                    prompt_version='plan_summary_prompt/3',attempts=1),compact=compact)
        profile('faults');fake=Fake();service.provider=fake
        key=str(uuid4());result=service.create(token,run,request,key,csrf)
        assert result.result.source=='model_presentation'
        assert service.create(token,run,request,key,csrf)==result and fake.calls==1
        with Session(state[1]) as fresh:retained=decode_summary(fresh.get(PlanSummaryGeneration,result.generation_id))
        try:service._publish(retained,result.result,token=token,csrf=csrf)
        except Exception as error:assert error.code=='STALE_SUMMARY_CLAIM'
        else:raise AssertionError('Late writer accepted')
        # Real lost terminal ACK: commit happens before the recognized injected error.
        import psycopg
        from sqlalchemy.exc import OperationalError
        profile('lostack');original=Session.commit;fired=[]
        def commit(session):
            original(session)
            if session.info.get('summary_transition')=='completed' and not fired:
                fired.append(1)
                raise OperationalError('COMMIT',{},psycopg.OperationalError('S2 synthetic lost ACK'),connection_invalidated=True)
        Session.commit=commit
        try:
            ackkey=str(uuid4());ack=service.create(token,run,request,ackkey,csrf)
            assert service.create(token,run,request,ackkey,csrf)==ack and fired==[1]
        finally:Session.commit=original
        # Same-key concurrent acceptance and provider outside the connection pool.
        profile('concurrency');entered,released=Event(),Event()
        class Waiting(Fake):
            def present(self,*args):
                assert state[1].pool.checkedout()==0
                entered.set();assert released.wait(20)
                return super().present(*args)
        waiting=Waiting();service.provider=waiting;concurrentkey=str(uuid4())
        with ThreadPoolExecutor(max_workers=2) as pool:
            future=pool.submit(service.create,token,run,request,concurrentkey,csrf)
            assert entered.wait(20)
            try:
                try:service.create(token,run,request,concurrentkey,csrf)
                except Exception as error:assert error.code=='GENERATION_IN_PROGRESS'
                else:raise AssertionError('Concurrent request accepted')
            finally:released.set()
            concurrent=future.result(timeout=25)
        assert waiting.calls==1
        # Current-rights revocation during provider work discards the response.
        with Session(state[1]) as s:
            member=s.scalar(select(StoreMembership).where(StoreMembership.store_id==UUID(int=1)))
            mid=member.id;member.role='STAFF'
            for right in READ_PERMISSIONS:s.add(MembershipGrant(membership_id=mid,permission=right))
            s.commit()
        profile('revoked')
        class Revoke(Fake):
            def present(self,*args):
                value=super().present(*args)
                with Session(state[1]) as s:s.delete(s.get(MembershipGrant,(mid,'budget.read')));s.commit()
                return value
        service.provider=Revoke()
        try:
            try:service.create(token,run,request,str(uuid4()),csrf)
            except Exception as error:assert error.code=='PERMISSION_DENIED'
            else:raise AssertionError('Revoked response delivered')
            try:service.read(token,run,result.generation_id)
            except Exception as error:assert error.code=='PERMISSION_DENIED'
            else:raise AssertionError('Revoked read delivered')
        finally:
            with Session(state[1]) as s:
                s.get(StoreMembership,mid).role='OWNER'
                for right in READ_PERMISSIONS:
                    row=s.get(MembershipGrant,(mid,right))
                    if row:s.delete(row)
                s.commit()
        # Existing crash/restart acceptance against profile/4, no network adapter.
        from app.models import PlanningRun
        from app.application.contracts.planning_run import PlanningRunRecord
        with Session(state[1]) as fresh:record=PlanningRunRecord.model_validate(fresh.get(PlanningRun,run).record_json,context={'retained_consistency':True})
        headers={'Origin':origin,'X-CSRF-Token':csrf,'Idempotency-Key':str(uuid4())}
        from app.infrastructure.planning_process import liveness
        with Session(state[1]) as fresh:
            interrupted=[decode_summary(row) for row in fresh.scalars(select(PlanSummaryGeneration).where(
                PlanSummaryGeneration.run_id==run,PlanSummaryGeneration.status=='running'))
                if row.record_json['profile']['model']=='mock-qwen']
        for abandoned in interrupted:
            assert liveness(abandoned.process)=='DEAD'
            service._publish(abandoned,error='PROCESS_INTERRUPTED',token=token,csrf=csrf)
        test_dead_process_explicit_replay_never_reissues_provider_attempt((state,record,service,headers,case['request'],path),'summary_profile/4')
        # Cold process read of a profile/4 result with no provider available.
        code='''
import os,json
from uuid import UUID
from datetime import datetime,timezone
from app.config import Settings
from app.infrastructure.database.engine import create_database_engine
from app.application.use_cases.auth import AuthUseCases
from app.application.use_cases.planning_public import PublicPlanning
from app.application.use_cases.plan_summary import PlanSummaries
from app.application.contracts.plan_summary import SummaryProfile
e=create_database_engine(Settings(_env_file=None));a=AuthUseCases(e,clock=lambda:datetime(2026,10,10,2,tzinfo=timezone.utc))
class Off:
 def present(self,*a):raise AssertionError('Cold read called provider')
s=PlanSummaries(PublicPlanning(a,None),SummaryProfile(model='UNCONFIGURED'),Off())
print(json.dumps(s.read(os.environ['S2_SESSION'],UUID(os.environ['S2_RUN']),UUID(os.environ['S2_GENERATION'])).model_dump(mode='json')))
e.dispose()
'''
        child=subprocess.run([sys.executable,'-B','-c',code],capture_output=True,text=True,timeout=30,
            env={**os.environ,'S2_SESSION':token,'S2_RUN':str(run),'S2_GENERATION':str(result.generation_id)})
        assert child.returncode==0,child.stderr
        assert json.loads(child.stdout)==result.model_dump(mode='json')
        # Every retained paid generation, including older source pins, still reads.
        for final in ROOT.glob('attempt-*/final.json'):
            observed=json.loads(final.read_text(encoding='utf8'));data=observed['response']
            assert service.read(token,UUID(data['run_id']),UUID(data['generation_id'])).model_dump(mode='json')==data
        # Foreign Store holder cannot read this generation.
        email='s2-foreign-'+str(uuid4())+'@example.test';setup(state,email=email);login(state,email=email)
        assert state[5].get(path+'/'+str(result.generation_id)).status_code==404
        assert ledger()==before,'Offline verification touched paid ledger'
        report=dict(source=fingerprint()[0],mode='OFFLINE_REAL_HTTP_PG_FAKE_PROVIDER',fresh_read=True,cold_process=True,
            replay_no_provider=True,current_rights_revocation=True,store_isolation=True,concurrency=True,
            lost_ack=True,late_writer_fenced=True,dead_process_restart=True,old_generations_preserved=True)
        write(ROOT/'final-source-offline-verification.json',report)
        print(json.dumps(report))
    finally:
        try:next(gen)
        except StopIteration:pass


if __name__=='__main__':main()
