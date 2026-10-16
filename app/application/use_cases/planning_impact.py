"""Bounded E4 orchestration in owned private runtime; no DB, training or live state."""
from pathlib import Path
from time import monotonic
import platform

from app.application.contracts.planning_impact import ImpactPlan, ImpactRun
from app.application.contracts.planning_impact import RealizedImpact
from app.application.contracts.forecast_benchmark import BenchmarkDataset
from app.application.contracts.procurement_selection import WinnerSelection
from app.application.forecast_challenger_serialization import challenger_digest
from app.application.planning_impact import planning_request, plan_forecast, realized_evaluation, report_runs
from app.application.planning_impact_oracle import finite_oracle
from app.infrastructure.forecast_benchmark_storage import BenchmarkStorage
from app.infrastructure.forecast_challenger_runtime import current_runtime
from app.infrastructure.planning_impact_source import load_e3, source_identity
from app.infrastructure.procurement_milp_v2 import NativeProductSearch


class ImpactBudgetExceeded(RuntimeError):
    pass


class ImpactBudget:
    def __init__(self, storage, directory, plan):
        self.storage,self.directory,self.plan=storage,directory,plan
        self.started=monotonic();self.spent=0.;self.solves=0;self.exhausted=False
        for file in directory.glob('resource-*.json'):
            row=storage.load(directory,file.name)
            self.spent=max(self.spent,row['seconds']);self.solves=max(self.solves,row['solves'])

    def check(self):
        if self.spent+monotonic()-self.started>=self.plan.wall_seconds:
            self.exhausted=True
            raise ImpactBudgetExceeded('WALL_BUDGET_EXCEEDED')

    def retain(self):
        row=dict(seconds=self.spent+monotonic()-self.started,solves=self.solves)
        digest=challenger_digest('impact-resource',row)
        self.storage.retain(self.directory,f'resource-{digest}.json',row)

    def factory(self, request, offers):
        guard=self
        self.check()
        native=NativeProductSearch(request,offers)
        class MeteredSearch:
            def solve(self,strategy,phase,deadline):
                guard.check()
                if guard.solves>=guard.plan.maximum_native_solves:
                    guard.exhausted=True
                    raise ImpactBudgetExceeded('NATIVE_SOLVE_BUDGET_EXCEEDED')
                guard.solves+=1
                guard.retain()
                return native.solve(strategy,phase,deadline)
            def accept(self,*args,**kwargs): return native.accept(*args,**kwargs)
            def exclude(self,*args,**kwargs): return native.exclude(*args,**kwargs)
        return MeteredSearch()


class PlanningImpact:
    def __init__(self,root:Path):
        self.root=root.resolve()
        self.storage=BenchmarkStorage(self.root/'runtime/challenger/planning-impact')

    def freeze(self,e3_experiment):
        from tests.fixtures.forecast_engine.planning_impact_setup import FIXTURES, operational_snapshot
        data,e3,bindings=load_e3(self.root,e3_experiment,native_replay=True)
        plan=ImpactPlan(e3_experiment=e3_experiment,dataset_digest=e3.dataset_digest,protocol_digest=e3.protocol_digest,
            forecasts=bindings,snapshots=tuple(operational_snapshot(t.origin,data.products,data.timezone,f)
                                             for t in e3.tasks for f in FIXTURES))
        source,hashes=source_identity(self.root)
        runtime=current_runtime()
        identity=challenger_digest('impact-experiment',dict(plan=plan,source=source,runtime=runtime))
        directory=self.storage.path('experiments',identity)
        self.storage.retain(directory,'plan.json',plan)
        self.storage.retain(directory,'dataset.json',data)
        self.storage.retain(directory,'environment.json',dict(source=source,hashes=hashes,runtime=runtime,
            python=platform.python_version(),run_order=plan.run_order,repetitions=1,
            limitation='Post-hoc synthetic forecasts and operational snapshots; not historical publication/deployment evidence.'))
        return dict(status='FROZEN',experiment_identity=identity,e3_experiment=e3_experiment,
                    runs=48,maximum_native_solves=576,wall_seconds=300,snapshot_count=16)

    def load(self,experiment):
        directory=self.storage.path('experiments',experiment)
        plan=ImpactPlan.model_validate(self.storage.load(directory,'plan.json'))
        env=self.storage.load(directory,'environment.json')
        source,_=source_identity(self.root)
        if source!=env['source'] or current_runtime().model_dump(mode='json')!=env['runtime']:
            raise ValueError('IMPACT_SOURCE_OR_RUNTIME_CHANGED')
        expected=challenger_digest('impact-experiment',dict(plan=plan,source=source,runtime=current_runtime()))
        if expected!=experiment: raise ValueError('IMPACT_EXPERIMENT_IDENTITY_MISMATCH')
        data,e3,bindings=load_e3(self.root,plan.e3_experiment)
        if bindings!=plan.forecasts or data!=BenchmarkDataset.model_validate(self.storage.load(directory,'dataset.json')):
            raise ValueError('E3_IMPACT_BINDINGS_CHANGED')
        return directory,plan,data,source

    def key(self,snapshot,binding,source):
        request=planning_request(snapshot,binding)
        input_digest=challenger_digest('impact-planning-input',request)
        snapshot_digest=challenger_digest('impact-snapshot',snapshot)
        key=challenger_digest('impact-run',dict(snapshot=snapshot_digest,forecast=binding.output_digest,
                                            planning_input=input_digest,source=source))
        return key,request,input_digest,snapshot_digest

    def evaluated(self,run,data,directory):
        if run.selection is None: return run
        realized=realized_evaluation(data,run.binding.checkpoint,run.selection)
        self.storage.retain(self.storage.path('runs',run.identity),f'realized-{realized.target_digest}.json',realized)
        return ImpactRun.model_validate(run.model_dump(mode='python')|dict(realized=realized))

    def run(self,experiment,*,smoke=False):
        directory,plan,data,source=self.load(experiment)
        guard=ImpactBudget(self.storage,directory,plan)
        runs=[];stop=False
        snapshots=plan.snapshots[:1] if smoke else plan.snapshots
        for snapshot in snapshots:
            for binding in (b for b in plan.forecasts if b.checkpoint.origin==snapshot.origin):
                key,request,input_digest,snapshot_digest=self.key(snapshot,binding,source)
                run_directory=self.storage.path('runs',key)
                old=self.storage.load(run_directory,'planning.json')
                if old is not None:
                    run=ImpactRun.model_validate(old)
                    self.verify_run(run,request,key,input_digest,snapshot_digest)
                else:
                    started=monotonic();selection=None;reason=None;status='COMPLETED'
                    try:
                        guard.check()
                        selection=plan_forecast(request,guard.factory)
                        if guard.exhausted: raise ImpactBudgetExceeded('COOPERATIVE_BUDGET_EXCEEDED')
                        if selection.comparison.source.execution in ('ERROR','BLOCKED','NUMERIC_UNSUPPORTED'):
                            status='TECHNICAL_FAILURE';reason='HOST_'+selection.comparison.source.execution
                    except Exception as error:
                        status='BUDGET_EXCEEDED' if isinstance(error,ImpactBudgetExceeded) else 'TECHNICAL_FAILURE'
                        reason=str(error) if isinstance(error,ImpactBudgetExceeded) else 'PLANNING_FAILED_'+type(error).__name__
                        stop=True
                    finally:
                        guard.retain()
                    run=ImpactRun(identity=key,snapshot_digest=snapshot_digest,forecast_output_digest=binding.output_digest,
                        planning_input_digest=input_digest,binding=binding,snapshot=snapshot,status=status,reason=reason,
                        selection=selection,realized=None,elapsed_seconds=monotonic()-started)
                    self.storage.retain(run_directory,'planning.json',run)
                if run.status=='COMPLETED':
                    run=self.evaluated(run,data,directory)
                    if snapshot.origin==plan.snapshots[0].origin and snapshot.fixture_id!='bounded_unproven':
                        oracle=finite_oracle(request,run.selection.comparison.source)
                        self.storage.retain(run_directory,'oracle.json',oracle)
                runs.append(run)
                self.storage.retain(directory,f'run-{key}.json',dict(identity=key,status=run.status))
                guard.retain()
                if stop: break
            if stop: break
        report=report_runs(runs,expected=3 if smoke else plan.maximum_runs)
        if smoke and report['status']=='COUNTERFACTUAL_SYNTHETIC_VERIFIED': report['status']='SMOKE_VERIFIED'
        report.update(experiment_identity=experiment,smoke_only=smoke,resource_native_solves=guard.solves,
                      budget_wall_seconds=guard.spent+monotonic()-guard.started)
        digest=challenger_digest('impact-report',report)
        self.storage.retain(directory,f'report-{digest}.json',report)
        return report

    def verify_run(self,run,request,key,input_digest,snapshot_digest):
        if (run.identity,run.planning_input_digest,run.snapshot_digest)!=(key,input_digest,snapshot_digest):
            raise ValueError('IMPACT_CHECKPOINT_IDENTITY_MISMATCH')
        if run.selection is not None and run.selection.comparison.source.input!=request:
            raise ValueError('IMPACT_RETAINED_PLANNING_INPUT_MISMATCH')

    def replay(self,experiment):
        from app.application.use_cases.procurement_v2 import evaluate_basket_v2
        from app.application.use_cases.procurement_selection import compare_procurement_v2, select_winner
        directory,plan,data,source=self.load(experiment)
        count=0;realized_count=0
        for snapshot in plan.snapshots:
            for binding in (b for b in plan.forecasts if b.checkpoint.origin==snapshot.origin):
                key,request,input_digest,snapshot_digest=self.key(snapshot,binding,source)
                retained=self.storage.load(self.storage.path('runs',key),'planning.json')
                if retained is None: raise ValueError('IMPACT_REPLAY_INCOMPLETE')
                run=ImpactRun.model_validate(retained)
                self.verify_run(run,request,key,input_digest,snapshot_digest)
                if run.status!='COMPLETED' or run.selection is None: raise ValueError('IMPACT_REPLAY_NONCOMPLETE')
                for strategy in run.selection.comparison.source.strategies:
                    candidate=strategy.candidate
                    if candidate is not None and evaluate_basket_v2(request,candidate.counts)!=candidate:
                        raise ValueError('IMPACT_FIXED_BASKET_REPLAY_MISMATCH')
                if select_winner(compare_procurement_v2(run.selection.comparison.source))!=run.selection:
                    raise ValueError('IMPACT_SELECTION_REPLAY_MISMATCH')
                realized=realized_evaluation(data,binding.checkpoint,run.selection)
                retained_realized=self.storage.load(self.storage.path('runs',key),f'realized-{realized.target_digest}.json')
                if realized!=RealizedImpact.model_validate(retained_realized):
                    raise ValueError('IMPACT_REALIZED_REPLAY_MISMATCH')
                count+=1;realized_count+=realized.simulation is not None
        report=dict(status='EXACT_FIXED_BASKET_REPLAY_VERIFIED',runs=count,complete_primary_ledgers=realized_count,
                    procurement_solves=0,experiment_identity=experiment)
        self.storage.retain(directory,'replay.json',report)
        return report
