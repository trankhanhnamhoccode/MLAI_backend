"""Explicit E3 offline freeze/smoke/run/rescore/replay orchestration; no operational DB."""
from datetime import datetime, timezone
from decimal import Decimal
import json
import hashlib
from pathlib import Path
from time import monotonic

from app.application.contracts.forecast_benchmark import ARMS, PROTOCOL_DIGEST, DEMO_ABC_PROTOCOL_DIGEST, ArmCheckpoint, BenchmarkDataset, BenchmarkPlan
from app.application.contracts.forecast_challenger import ChallengerError
from app.application.forecast_benchmark_admission import admit_plan
from app.application.forecast_benchmark_reporting import summary, attach_targets
from app.application.forecast_challenger_serialization import challenger_digest
from app.application.use_cases.forecast_challenger import ForecastChallenger
from app.infrastructure.forecast_challenger_runtime import current_runtime
from app.infrastructure.storage.forecast_challenger import ChallengerStorage
from app.infrastructure.forecast_benchmark_storage import BenchmarkStorage, FitBudget, BudgetExceeded, training_source_identity, host_source_identity
from app.infrastructure.forecast_benchmark_training import fit_arm, fit_identity


def load_protocol(root:Path,plan:BenchmarkPlan|None=None):
    # Reuse the existing E1 offline validator without changing its frozen contract.
    from scripts.forecast_benchmark_protocol import validate_manifest, canonical_digest
    payload=json.loads((root/'tests/fixtures/forecast_engine/benchmark_manifest.json').read_bytes())
    validate_manifest(payload)
    if canonical_digest(payload)!=PROTOCOL_DIGEST:
        raise ValueError('FROZEN_PROTOCOL_DIGEST_MISMATCH')
    if plan is not None and plan.harness_version=='causal_benchmark/3':
        revised=json.loads((root/'tests/fixtures/forecast_engine/benchmark_manifest_demo_v3.json').read_bytes())
        if (canonical_digest(revised)!=DEMO_ABC_PROTOCOL_DIGEST or revised['base_protocol_digest']!=PROTOCOL_DIGEST or
            revised['arm_configuration']!=payload['arm_configuration'] or revised['tasks']!=[t.model_dump(mode='json') for t in plan.tasks]):
            raise ValueError('FROZEN_DEMO_PROTOCOL_CHANGED')
        return revised
    return payload


class ForecastBenchmark:
    def __init__(self,root:Path):
        self.root=root.resolve()
        self.storage=BenchmarkStorage(self.root/'runtime/challenger/benchmarks')
        self.artifacts=ChallengerStorage(self.root/'runtime/challenger')

    def freeze(self,data:BenchmarkDataset,plan:BenchmarkPlan):
        admit_plan(data,plan)
        protocol=load_protocol(self.root,plan)
        runtime=current_runtime()
        if plan.harness_version!='causal_benchmark/1':
            runtime_identity=dict(runtime=runtime,host_source=host_source_identity())
        else: runtime_identity=runtime
        identity=challenger_digest('experiment',{'plan':plan,'runtime':runtime_identity,'training_source':training_source_identity()})
        directory=self.storage.path('experiments',identity)
        host_paths=['app/infrastructure/forecast_model.py','app/domain/forecasting/baseline.py',
                    'app/domain/forecasting/features.py','app/domain/forecasting/stockout.py',
                    'app/application/forecast_demand.py','app/application/forecast_serialization.py',
                    'app/application/use_cases/forecast_baseline.py']
        host_hashes={p:hashlib.sha256((self.root/p).read_bytes()).hexdigest() for p in host_paths}
        # Existing receipts from the initial run bind its host source without refitting.
        for receipt in directory.glob('execution-source-*.json'):
            recorded=self.storage.load(directory,receipt.name)
            if any(recorded.get(p)!=v for p,v in host_hashes.items()):
                raise ValueError('BENCHMARK_HOST_SOURCE_CHANGED')
        self.storage.retain(directory,'host-source.json',host_hashes)
        if any(directory.glob('execution-source-*.json')):
            for task in plan.tasks:
                for arm in plan.configuration_ids:
                    key=fit_identity(data,plan,task,arm,protocol['arm_configuration'][arm])
                    fit_directory=self.storage.path('fits',key)
                    if self.storage.load(fit_directory,'checkpoint.json') is not None:
                        self.storage.retain(fit_directory,'host-source.json',host_hashes)
        self.storage.retain(directory,'dataset.json',data)
        self.storage.retain(directory,'plan.json',plan)
        self.storage.retain(directory,'environment.json',{'runtime':runtime,'training_source':training_source_identity(),
            'protocol_digest':plan.protocol_digest,'dataset_digest':plan.dataset_digest,
            'origin_count':len(plan.tasks),'configuration_ids':plan.configuration_ids,'configurations_per_arm':1,
            'maximum_booster_fits':plan.budget.maximum_booster_fits,'maximum_postprocess_fits':plan.budget.maximum_postprocess_fits,
            'wall_budget_seconds':plan.budget.wall_seconds})
        return identity,directory,protocol

    def run(self,data:BenchmarkDataset,plan:BenchmarkPlan,*,smoke=False):
        identity,directory,protocol=self.freeze(data,plan)
        retained=self.storage.load(directory,'summary.json')
        if not smoke and retained is not None and retained['status'] in ('SYNTHETIC_CORRECTNESS','EXPLORATORY'):
            self.replay(identity)
            report=self.rescore(identity)
            report.update(reused_completed_run=True,booster_fits_spent=retained['booster_fits_spent'],
                          postprocess_fits_spent=retained['postprocess_fits_spent'])
            return report
        completed=[]
        spent=0;booster_count=0;post_count=0
        for task in plan.tasks:
            for arm in plan.configuration_ids:
                key=fit_identity(data,plan,task,arm,protocol['arm_configuration'][arm])
                old=self.storage.load(self.storage.path('fits',key),'checkpoint.json')
                if old is not None:
                    c=ArmCheckpoint.model_validate(old)
                    spent+=float(c.training_seconds)+float(c.inference_seconds)
                    booster_count+=0 if arm==ARMS[0] else 3
                    post_count+=2 if arm==ARMS[2] else 0
        for receipt in directory.glob('resource-ledger-*.json'):
            ledger=self.storage.load(directory,receipt.name)
            spent=max(spent,float(ledger['spent_seconds']))
            booster_count=max(booster_count,ledger['boosters'])
            post_count=max(post_count,ledger['postprocess'])
        from app.infrastructure.forecast_benchmark_features import NativeFrameCache
        guard=FitBudget(plan.budget,spent_seconds=spent,boosters=booster_count,postprocess=post_count,
            native_cache=NativeFrameCache() if plan.harness_version=='causal_benchmark/3' else None)
        tasks=plan.tasks[:1] if smoke else plan.tasks
        budget_exceeded=False
        for task in tasks:
            for arm in plan.configuration_ids:
                try:
                    guard.check()
                    checkpoint,reused=fit_arm(data,plan,task,arm,protocol['arm_configuration'][arm],
                                             guard,self.storage,self.artifacts)
                    if reused:
                        frozen_host=self.storage.load(directory,'host-source.json')
                        fit_host=self.storage.load(self.storage.path('fits',checkpoint.identity),'host-source.json')
                        if fit_host!=frozen_host:
                            raise ValueError('BENCHMARK_FIT_HOST_SOURCE_UNKNOWN_OR_CHANGED')
                        from app.infrastructure.forecast_benchmark_replay import replay_checkpoint
                        replay_checkpoint(data,plan,task,checkpoint,protocol['arm_configuration'][arm],
                                          self.storage,self.artifacts)
                    else:
                        self.storage.retain(self.storage.path('fits',checkpoint.identity),'host-source.json',
                                            self.storage.load(directory,'host-source.json'))
                except Exception as error:
                    status=('BUDGET_EXCEEDED' if isinstance(error,BudgetExceeded) else
                            'DATA_BLOCKED' if isinstance(error,ChallengerError) and error.category.value=='DATA_BLOCKED'
                            else 'TECHNICAL_FAILURE')
                    checkpoint=ArmCheckpoint(arm=arm,origin=task.origin,
                        identity=fit_identity(data,plan,task,arm,protocol['arm_configuration'][arm]),
                        status=status,
                        reason=error.code if isinstance(error,ChallengerError) else str(error) if isinstance(error,BudgetExceeded) else 'FIT_FAILED_'+type(error).__name__,
                        predictions=(),input_digest=plan.dataset_digest,training_seconds=Decimal(0),inference_seconds=Decimal(0))
                    budget_exceeded=isinstance(error,BudgetExceeded)
                finally:
                    ledger={'spent_seconds':guard.spent_seconds+monotonic()-guard.started,
                            'boosters':guard.boosters,'postprocess':guard.postprocess}
                    key=challenger_digest('resource-ledger',ledger)
                    self.storage.retain(directory,f'resource-ledger-{key}.json',ledger)
                completed.append(checkpoint)
                self.storage.retain(directory,f'{task.origin}-{arm}.json',checkpoint)
                if budget_exceeded:
                    break
            if budget_exceeded:
                break
        complete=len(completed)==len(plan.tasks)*len(plan.configuration_ids) and all(c.status=='COMPLETED' for c in completed)
        report=summary(data,plan,tuple(completed),complete=complete)
        if smoke and len(completed)==len(plan.configuration_ids) and all(c.status=='COMPLETED' for c in completed):
            report['status']='SMOKE_VERIFIED'
        report.update(experiment_identity=identity,protocol_digest=plan.protocol_digest,dataset_digest=plan.dataset_digest,
                      booster_fits_spent=guard.boosters,postprocess_fits_spent=guard.postprocess,smoke_only=smoke)
        self._source_record(directory)
        self.storage.retain(directory,'smoke-summary.json' if smoke else 'summary.json',report)
        self.storage.retain(directory,'smoke-predictions.json' if smoke else 'predictions.json',
                            tuple(p for c in completed for p in attach_targets(data,c)))
        return report

    def _source_record(self,directory):
        paths=['app/application/use_cases/forecast_benchmark.py','app/application/forecast_benchmark_reporting.py',
               'app/domain/forecasting/benchmark_metrics.py','app/infrastructure/forecast_benchmark_storage.py',
               'app/infrastructure/forecast_model.py','app/domain/forecasting/baseline.py',
               'app/domain/forecasting/features.py','app/domain/forecasting/stockout.py',
               'app/application/forecast_demand.py','app/application/forecast_serialization.py',
               'app/application/use_cases/forecast_baseline.py','scripts/forecast_benchmark.py']
        paths.append('app/infrastructure/forecast_benchmark_replay.py')
        hashes={p:hashlib.sha256((self.root/p).read_bytes()).hexdigest() for p in paths}
        digest=challenger_digest('execution-source',hashes)
        self.storage.retain(directory,f'execution-source-{digest}.json',hashes)
        return digest

    def rescore(self,experiment:str):
        directory=self.storage.path('experiments',experiment)
        data=BenchmarkDataset.model_validate(self.storage.load(directory,'dataset.json'))
        plan=BenchmarkPlan.model_validate(self.storage.load(directory,'plan.json'))
        expected,_,_=self.freeze(data,plan)
        if expected!=experiment:
            raise ValueError('BENCHMARK_SOURCE_OR_RUNTIME_CHANGED')
        checkpoints=[]
        for task in plan.tasks:
            for arm in plan.configuration_ids:
                row=self.storage.load(directory,f'{task.origin}-{arm}.json')
                if row is not None:
                    checkpoints.append(ArmCheckpoint.model_validate(row))
        complete=len(checkpoints)==len(plan.tasks)*len(plan.configuration_ids) and all(c.status=='COMPLETED' for c in checkpoints)
        report=summary(data,plan,tuple(checkpoints),complete=complete)
        report.update(experiment_identity=experiment,protocol_digest=plan.protocol_digest,dataset_digest=plan.dataset_digest,
                      rescore_without_training=True)
        digest=self._source_record(directory)
        self.storage.retain(directory,f'rescored-{digest}.json',report)
        return report

    def replay(self,experiment:str,*,dedicated:bool=False):
        from app.infrastructure.forecast_readonly_replay import replay
        return replay(self.root,experiment,dedicated=dedicated)
