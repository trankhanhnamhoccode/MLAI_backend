"""Isolated read-only replay against byte-pinned historical app/source and runtime."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(workspace:Path,snapshot:Path,experiment:str,*,dedicated=False):
    # Parent verifies Git provenance; worker independently checks every snapshot byte.
    manifest=json.loads((snapshot/'source.json').read_bytes())
    for name,digest in manifest['files'].items():
        if hashlib.sha256((snapshot/name).read_bytes()).hexdigest()!=digest:raise ValueError('HISTORICAL_SOURCE_TAMPERED')
    if manifest['experiment']!=experiment:raise ValueError('HISTORICAL_EXPERIMENT_MISMATCH')
    sys.path.insert(0,str(snapshot))
    import platform
    platform.uname()
    from scripts.run_demo_benchmark import install_offline_guard
    attempts=install_offline_guard()
    import lightgbm as lgb
    def forbidden(*a,**k):raise RuntimeError('REPLAY_TRAINING_FORBIDDEN')
    lgb.train=forbidden
    from app.application.contracts.forecast_benchmark import BenchmarkBudget,BenchmarkPlan,BenchmarkDataset,ArmCheckpoint,ARMS
    from app.application.forecast_challenger_serialization import canonical_bytes,challenger_digest
    from app.application.forecast_benchmark_admission import admit_plan
    from app.application.use_cases.forecast_benchmark import ForecastBenchmark,load_protocol
    from app.infrastructure.forecast_benchmark_storage import BenchmarkStorage,training_source_identity,host_source_identity
    from app.infrastructure.forecast_benchmark_replay import replay_checkpoint
    from app.infrastructure.forecast_challenger_runtime import current_runtime
    from app.infrastructure.storage.forecast_challenger import ChallengerStorage
    boundary=load_module('current_plan_boundary',workspace/'app/application/forecast_benchmark_plan.py')
    class ReplayBudget(BenchmarkBudget):
        wall_seconds: boundary.ResourceSeconds = 300
    class ReplayPlan(BenchmarkPlan):
        budget: ReplayBudget = ReplayBudget()
    class ReadOnlyStorage(BenchmarkStorage):
        def retain(self,directory,name,value):
            existing=self.load(directory,name)
            if existing is None or canonical_bytes(existing)!=canonical_bytes(value):
                raise ValueError('READONLY_REPLAY_REFUSES_PUBLICATION:'+name)
    storage=ReadOnlyStorage(workspace/'runtime/challenger/benchmarks')
    directory=storage.path('experiments',experiment)
    env=storage.load(directory,'environment.json')
    plan=boundary.restore_plan(storage.load(directory,'plan.json'),ReplayPlan)
    data=BenchmarkDataset.model_validate(storage.load(directory,'dataset.json'))
    admit_plan(data,plan)
    protocol=load_protocol(snapshot,plan)
    runtime=current_runtime()
    if env['training_source']!=training_source_identity() or env['runtime']!=runtime.model_dump(mode='json'):
        raise ValueError('HISTORICAL_TRAINING_SOURCE_OR_RUNTIME_MISMATCH')
    runtime_identity=runtime if plan.harness_version=='causal_benchmark/1' else dict(runtime=runtime,host_source=host_source_identity())
    if challenger_digest('experiment',dict(plan=plan,runtime=runtime_identity,training_source=training_source_identity()))!=experiment:
        raise ValueError('HISTORICAL_EXPERIMENT_IDENTITY_MISMATCH')
    host=storage.load(directory,'host-source.json')
    for path,expected in host.items():
        if hashlib.sha256((snapshot/path).read_bytes()).hexdigest()!=expected:raise ValueError('PINNED_HOST_SOURCE_CHANGED')
    receipts=list(directory.glob('execution-source-*.json'))
    if not receipts:raise ValueError('HISTORICAL_EXECUTION_SOURCE_REQUIRED')
    for receipt in receipts:
        for path,expected in storage.load(directory,receipt.name).items():
            if hashlib.sha256((snapshot/path).read_bytes()).hexdigest()!=expected:raise ValueError('PINNED_EXECUTION_SOURCE_CHANGED')
    artifacts=ChallengerStorage(workspace/'runtime/challenger')
    identities=[];native=0
    for task in plan.tasks:
        for arm in plan.configuration_ids:
            c=ArmCheckpoint.model_validate(storage.load(directory,f'{task.origin}-{arm}.json'))
            fit=storage.path('fits',c.identity)
            if c!=ArmCheckpoint.model_validate(storage.load(fit,'checkpoint.json')):raise ValueError('FIT_CHECKPOINT_MISMATCH')
            if storage.load(fit,'host-source.json')!=host:raise ValueError('FIT_HOST_SOURCE_MISMATCH')
            identities.append(replay_checkpoint(data,plan,task,c,protocol['arm_configuration'][arm],storage,artifacts))
            native+=arm==ARMS[2]
    reference=None
    if dedicated:
        module=load_module('historical_dedicated_verifier',snapshot/'scripts/verify_demo_abc.py')
        class HistoricalService(ForecastBenchmark):
            def __init__(self,root):
                super().__init__(snapshot)
                self.storage=storage;self.artifacts=artifacts
        import app.application.use_cases.forecast_benchmark as historical_service_module
        historical_service_module.ForecastBenchmark=HistoricalService
        reference=module.verify(experiment)
    return dict(status='READONLY_GENERIC_REPLAY_VERIFIED',experiment_identity=experiment,replayed_arms=len(identities),
        native_artifacts=native,identities=identities,execution_source_commit=manifest['git_commit'],
        historical_source_identity=snapshot.name,verifier_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        plan_loader_sha256=hashlib.sha256((workspace/'app/application/forecast_benchmark_plan.py').read_bytes()).hexdigest(),
        source_mode='VERIFIED_HISTORICAL_SOURCE_WITH_CURRENT_TYPED_PLAN_LOADER',dedicated_reference=reference,
        training_calls=0,network_process_attempts=attempts,original_writes=0)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('workspace','snapshot'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--experiment',required=True);parser.add_argument('--dedicated',action='store_true')
    args=parser.parse_args()
    print(json.dumps(run(args.workspace.resolve(),args.snapshot.resolve(),args.experiment,dedicated=args.dedicated),default=str))


if __name__=='__main__':main()
