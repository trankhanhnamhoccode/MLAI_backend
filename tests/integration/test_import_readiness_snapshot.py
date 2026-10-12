"""New I06 post-write snapshots and legacy retained completion are immutable."""
from uuid import UUID,uuid4
import pytest
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from tests.integration.test_import_commit import imp,env,ready,commit,finished
from app.application.use_cases.readiness import ReadinessReads
from app.models import SalesDaily
from app.models.import_staging import ImportBatch,ImportJob,ImportAudit
from app.application.import_identity import content_digest


def test_new_completion_pins_post_write_projection_and_never_recalculates(imp,monkeypatch):
    ident,preview,revision=ready(imp)
    value=finished(imp,ident,commit(imp,ident,preview,revision))
    projection=value['readiness']
    assert projection['evaluated_actions']==['import','menu','inventory']
    assert all(a['availability']=='ready' for a in projection['actions'])
    with Session(imp[0][1]) as s:
        row=s.scalar(select(SalesDaily));row.quantity=999;s.commit()
    monkeypatch.setattr(ReadinessReads,'completion_in_transaction',lambda *a:pytest.fail('GET recomputed readiness'))
    assert imp[0][5].get('/api/v1/imports/'+ident+'/completion').json()['data']==value
    with Session(imp[0][1]) as s:
        assert s.get(ImportBatch,UUID(ident)).analysis_json['completion']['readiness']==projection


def test_projection_storage_failure_rolls_back_canonical_and_success_completion(imp,monkeypatch):
    ident,preview,revision=ready(imp)
    accepted=commit(imp,ident,preview,revision)
    def fail(*args):raise RuntimeError('projection storage failed')
    monkeypatch.setattr(ReadinessReads,'completion_in_transaction',staticmethod(fail))
    with pytest.raises(RuntimeError,match='projection storage failed'):
        imp[2].run_one()
    with Session(imp[0][1]) as s:
        assert s.scalar(select(func.count()).select_from(SalesDaily))==0
        assert 'completion' not in s.get(ImportBatch,UUID(ident)).analysis_json
        assert s.scalar(select(func.count()).select_from(ImportAudit).where(ImportAudit.kind=='IMPORT_CANONICAL_COMMITTED'))==0
        assert s.get(ImportJob,UUID(accepted.json()['data']['job_id'])).status=='failed'


def test_legacy_completion_unknown_projection_preserved_on_read(imp,monkeypatch):
    from app.application.contracts.import_mapping import CompletionReadiness,CompletionActionReadiness
    original=ReadinessReads.completion_in_transaction
    def legacy(s,store,now,permissions):
        value=original(s,store,now,permissions)
        return value.model_copy(update={'actions':tuple(CompletionActionReadiness(action=a) for a in value.evaluated_actions)})
    monkeypatch.setattr(ReadinessReads,'completion_in_transaction',staticmethod(legacy))
    ident,preview,revision=ready(imp)
    value=finished(imp,ident,commit(imp,ident,preview,revision))
    assert all(a['availability']=='unknown' for a in value['readiness']['actions'])
    monkeypatch.setattr(ReadinessReads,'completion_in_transaction',staticmethod(original))
    assert imp[0][5].get('/api/v1/imports/'+ident+'/completion').json()['data']==value
