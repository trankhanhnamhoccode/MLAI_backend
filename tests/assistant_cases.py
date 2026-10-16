"""Static synthetic historical graphs; decode only, never execute business engines."""
import json
from pathlib import Path
from datetime import timedelta
from uuid import UUID
from functools import lru_cache

from app.application.contracts.planning_run import PlanningRunRecord
from app.application.planning_serialization import digest, request_digest, exact_json
from app.infrastructure.planning_process import current_process


def frozen_case(kind='stock'):
    raw = json.loads((Path(__file__).parent/'fixtures/decision_assistant'/f'{kind}.json').read_text(encoding='utf-8'))
    cache = {}
    def expand(value):
        if isinstance(value,dict) and set(value) == {'$node'}:
            key = value['$node']
            if key not in cache: cache[key] = {k:expand(v) for k,v in raw['nodes'][key].items()}
            return cache[key]
        if isinstance(value,list): return [expand(v) for v in value]
        return value
    return expand(raw['root'])


@lru_cache(maxsize=16)
def retained_record(kind='stock', *, actor_id=UUID(int=6001), public=True):
    data = frozen_case('stock' if kind=='failed-partial' else kind)
    pipeline = data['pipeline']
    failed=kind=='failed-partial'
    if failed:
        # Hand contract variant: one strategy fails after retaining a valid
        # incumbent. Interned source nodes preserve all nested source equality.
        pipeline['procurement']['execution']='ERROR'
        row=pipeline['procurement']['strategies'][2]
        row.update(execution='ERROR',diagnostic='Synthetic technical failure',search_complete=False,proof='UNPROVEN')
        pipeline['outcome']='EXECUTION_ERROR'
    capture = pipeline['capture']
    request = capture['request']
    declaration = {k:request[k] for k in ('forecast_run_id','inventory_scope','committed_inbound_state',
        'committed_inbound_provenance','no_additional_orders_provenance','snapshot_policy')}
    declaration.update({k:v for k,v in request['procurement'].items() if k not in
        ('policy','budget','budget_ceiling','budget_version')})
    from datetime import datetime
    at = datetime.fromisoformat(capture['captured_at'])
    accepted = at - timedelta(seconds=1)
    finish = at + timedelta(seconds=1)
    original = data['setup']['resolution']['request']
    raw = dict(storage_version='planning_storage/1',package_schema_version=1,run_id=UUID(int={'stock':7001,'purchase':7002,'infeasible':7003,'failed-partial':7004}[kind]),
        actor_id=actor_id,store_id=request['store_id'],operation='C02',key_digest=digest('fixture-key',kind),
        request_digest=request_digest(original),request=original,resolution=data['setup']['resolution'],
        accepted_at=accepted,started_at=accepted,finished_at=finish,status='failed' if failed else 'completed',
        claim=dict(token=UUID(int=8001),generation=1,process=current_process()),declarations=declaration,
        capture=capture,input_digest=None,result=pipeline,result_digest=None,
        outcome='execution_error' if failed else 'no_eligible_candidate' if kind=='infeasible' else 'recommendation_available',
        error_code='EXECUTION_ERROR' if failed else None,error_summary='Synthetic partial failure' if failed else None)
    # Use the repository's canonical numeric representation before role-separated
    # digest creation. This changes representation only, never retained facts.
    from app.application.contracts.decision_capture_v2 import DecisionCaptureOutcomeV2, OperationalPipelineResultV2
    typed_capture=DecisionCaptureOutcomeV2.model_validate(capture,context={'retained_consistency':True})
    typed_result=OperationalPipelineResultV2.model_validate(pipeline,context={'retained_consistency':True})
    raw.update(capture=typed_capture,result=typed_result,input_digest=digest('capture',typed_capture),result_digest=digest('result',typed_result))
    if public:
        raw['public_acceptance']=dict(session_digest='0'*64,authorization_version='synthetic-v1',
            serving=dict(version='synthetic-baseline-1',policy=dict(mode='BASELINE',artifact_identity=None,
                fallback_policy='ADR015_RECOGNIZED_ONLY',dependency_versions=())),receipt_warnings=())
        raw['public_audit']=tuple(dict(action=action,actor_id=actor_id,occurred_at=when) for action,when in
            [('ACCEPTED',accepted),('CLAIMED',accepted),('CAPTURE_RETAINED',at),('FAILED' if failed else 'COMPLETED',finish)])
    return PlanningRunRecord.model_validate(raw,context={'retained_consistency':True})


def row_for(record):
    from types import SimpleNamespace
    return SimpleNamespace(record_json=exact_json(record),record_digest=digest('aggregate',record),revision=1,
        id=record.run_id,actor_id=record.actor_id,store_id=record.store_id,operation=record.operation,
        key_digest=record.key_digest,request_digest=record.request_digest,status=record.status,accepted_at=record.accepted_at)


def realistic_record(*,actor_id=UUID(int=6001)):
    """Already-frozen two-option milk case; no engine/solver in test or chat reads."""
    raw=frozen_case('conversational_realistic')
    raw['actor_id']=str(actor_id)
    for row in raw['public_audit']:row['actor_id']=str(actor_id)
    return PlanningRunRecord.model_validate(raw,context={'retained_consistency':True})
