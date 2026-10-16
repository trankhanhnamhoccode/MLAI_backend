"""Fresh-process replay and future-label perturbation of actual /3 retained outputs."""
import argparse
import hashlib
from pathlib import Path
from decimal import Decimal

ROOT=Path(__file__).resolve().parents[1]


def restore_frozen_demo_plan(raw):
    """Validate first, then preserve the original integral default's JSON identity.

    Pydantic validates an explicit float field300 as300.0, whereas this frozen plan
    was constructed with the validated policy's default300. Never coerce other
    budgets or bypass contract validation to make an identity match.
    """
    from app.application.contracts.forecast_benchmark import BenchmarkPlan
    from app.application.forecast_challenger_serialization import canonical_bytes
    validated=BenchmarkPlan.model_validate(raw)
    if type(raw['budget']['wall_seconds']) is int and raw['budget']['wall_seconds']==300:
        normalized=raw|dict(budget={k:v for k,v in raw['budget'].items() if k!='wall_seconds'})
        validated=BenchmarkPlan.model_validate(normalized)
    if canonical_bytes(validated)!=canonical_bytes(raw):raise ValueError('FROZEN_PLAN_REPRESENTATION_MISMATCH')
    return validated


def verify(experiment:str):
    import platform
    platform.uname()
    from scripts.run_demo_benchmark import install_offline_guard
    attempts=install_offline_guard()
    import lightgbm as lgb
    def forbidden(*a,**k):raise RuntimeError('VERIFICATION_CANNOT_FIT')
    lgb.train=forbidden
    from app.application.contracts.forecast_benchmark import BenchmarkDataset,BenchmarkPlan,ArmCheckpoint,ARMS
    from app.application.contracts.forecast_challenger import ChallengerInput
    from app.application.forecast_benchmark_admission import at_origin,calendar_at_origin
    from app.application.forecast_challenger_serialization import canonical_bytes,challenger_digest
    from app.application.use_cases.forecast_benchmark import ForecastBenchmark
    from app.application.use_cases.forecast_challenger import ForecastChallenger
    from app.infrastructure.forecast_benchmark_training import fit_identity
    from app.infrastructure.forecast_challenger_runtime import current_runtime
    service=ForecastBenchmark(ROOT)
    directory=service.storage.path('experiments',experiment)
    data=BenchmarkDataset.model_validate(service.storage.load(directory,'dataset.json'))
    plan=restore_frozen_demo_plan(service.storage.load(directory,'plan.json'))
    frozen=service.storage.load(directory,'demo-freeze.json')
    for p,digest in frozen['source'].items():
        if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=digest:raise ValueError('FROZEN_SOURCE_CHANGED')
    expected,_,protocol=service.freeze(data,plan)
    if expected!=experiment:raise ValueError('FROZEN_EXPERIMENT_SOURCE_MISMATCH')
    from app.infrastructure.forecast_benchmark_replay import replay_checkpoint
    replayed=[]
    for task in plan.tasks:
        for arm in plan.configuration_ids:
            checkpoint=ArmCheckpoint.model_validate(service.storage.load(directory,f'{task.origin}-{arm}.json'))
            replayed.append(replay_checkpoint(data,plan,task,checkpoint,protocol['arm_configuration'][arm],service.storage,service.artifacts))
    task=plan.tasks[0]
    checkpoint=ArmCheckpoint.model_validate(service.storage.load(directory,f'{task.origin}-{ARMS[2]}.json'))
    from app.application.use_cases.forecast_benchmark import load_protocol
    config=load_protocol(ROOT,plan)['arm_configuration'][ARMS[2]]
    modified=data.model_dump(mode='python')
    for row in modified['observations']:
        if row['sales_date']>task.origin:row['quantity']=Decimal('999999')
    changed=BenchmarkDataset.model_validate(modified)
    if fit_identity(data,plan,task,ARMS[2],config)!=fit_identity(changed,plan,task,ARMS[2],config):
        raise ValueError('FUTURE_LABEL_CHANGED_EARLIER_FIT_IDENTITY')
    evidence=service.artifacts.load_evidence(checkpoint.replay_identity)
    input2=ChallengerInput.model_validate(evidence.input.model_dump(mode='python')|dict(
        observations=at_origin(changed,task.origin),calendar=calendar_at_origin(changed,task.origin)))
    if input2!=evidence.input:raise ValueError('FUTURE_LABEL_CHANGED_EARLIER_CAPTURE')
    bundle=service.artifacts.load_artifact(checkpoint.artifact_identity)
    computed=ForecastChallenger._compute(input2,bundle,current_runtime())
    if canonical_bytes(computed)!=canonical_bytes(evidence.output):raise ValueError('FUTURE_LABEL_CHANGED_EARLIER_PREDICTION')
    result=dict(status='REPLAY_AND_FUTURE_LABEL_INVARIANCE_VERIFIED',experiment_identity=experiment,
        replayed_checkpoints=len(replayed),native_artifacts=len(plan.tasks),
        plan_representation='validated original integral300 default preserved; generic loader float300.0 drift is not new source/data',
        altered_future_labels=sum(o.sales_date>task.origin for o in data.observations),
        representative_origin=task.origin,representative_native_predictions=len(computed.forecast.predictions),
        booster_fits=0,network_process_attempts=attempts,production='LOCKED',
        verification_source=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    identity=challenger_digest('demo-abc-verification',result)
    service.storage.retain(directory,'verify-'+identity+'.json',result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment',required=True)
    args=parser.parse_args()
    from app.application.forecast_challenger_serialization import canonical_bytes
    print(canonical_bytes(verify(args.experiment)).decode())


if __name__=='__main__':main()
