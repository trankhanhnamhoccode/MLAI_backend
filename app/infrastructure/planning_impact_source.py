"""Verify actual E3 retained identities/bytes before reusing forecasts, never train."""
from pathlib import Path
import hashlib

from app.application.contracts.forecast_benchmark import ARMS, ArmCheckpoint, BenchmarkDataset, BenchmarkPlan
from app.application.contracts.planning_impact import ImpactBinding
from app.application.forecast_challenger_serialization import challenger_digest
from app.application.use_cases.forecast_benchmark import ForecastBenchmark


def load_e3(root:Path, identity:str, *, native_replay=False):
    service=ForecastBenchmark(root)
    directory=service.storage.path('experiments',identity)
    data=BenchmarkDataset.model_validate(service.storage.load(directory,'dataset.json'))
    plan=BenchmarkPlan.model_validate(service.storage.load(directory,'plan.json'))
    expected,_,_=service.freeze(data,plan)
    if expected!=identity or data.classification!='SYNTHETIC':
        raise ValueError('E4_REQUIRES_EXPLICIT_SYNTHETIC_E3_IDENTITY')
    if native_replay: service.replay(identity)
    bindings=[]
    for task in plan.tasks:
        for arm in ARMS:
            c=ArmCheckpoint.model_validate(service.storage.load(directory,f'{task.origin}-{arm}.json'))
            retained=service.storage.load(service.storage.path('fits',c.identity),'checkpoint.json')
            if c!=ArmCheckpoint.model_validate(retained) or c.status!='COMPLETED':
                raise ValueError('E3_FIT_CHECKPOINT_MISMATCH')
            if c.arm==ARMS[2]:
                artifact=service.artifacts.load_artifact(c.artifact_identity)
                evidence=service.artifacts.load_evidence(c.replay_identity)
                if evidence is None or evidence.input.artifact_identity!=c.artifact_identity:
                    raise ValueError('E3_NATIVE_EVIDENCE_MISMATCH')
            bindings.append(ImpactBinding(checkpoint=c,output_digest=challenger_digest('e3-output',c.predictions)))
    return data,plan,tuple(bindings)


def source_identity(root):
    paths=set()
    for folder in ('app/domain/decision','app/domain/demand'):
        paths.update((root/folder).rglob('*.py'))
    for folder in ('app/application','app/application/contracts','app/application/use_cases'):
        for pattern in ('*procurement*.py','*serving*.py','*bom*.py','*decision*.py','planning_impact*.py'):
            paths.update((root/folder).glob(pattern))
    paths.update(root/p for p in ('app/application/contracts/common.py','app/application/contracts/inventory.py',
        'app/application/contracts/recipe.py','app/application/contracts/supplier.py',
        'app/infrastructure/procurement_milp_v2.py','app/infrastructure/procurement_milp.py',
        'app/infrastructure/planning_impact_source.py','app/application/use_cases/planning_impact.py',
        'tests/fixtures/forecast_engine/planning_impact_setup.py','scripts/procurement_demo_cases.py',
        'scripts/procurement_v2_demo_cases.py'))
    hashes={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}
    return challenger_digest('impact-source',hashes),hashes
