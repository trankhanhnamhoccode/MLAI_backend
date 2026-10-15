"""Fresh-process fixed-basket replay of all retained E4 cases, including a partial run.

No candidate search, procurement solve, training or operational DB access.
"""
import argparse
import hashlib
from pathlib import Path
from time import monotonic

from app.application.contracts.planning_impact import ImpactRun, RealizedImpact
from app.application.forecast_challenger_serialization import challenger_digest, canonical_bytes
from app.application.planning_impact import realized_evaluation
from app.application.use_cases.planning_impact import PlanningImpact
from app.application.use_cases.procurement_v2 import evaluate_basket_v2
from app.application.use_cases.procurement_selection import projected, selection_facts


def verify(root,experiment,*,wall_seconds=120):
    started=monotonic()
    service=PlanningImpact(root)
    directory,plan,data,source=service.load(experiment)
    count=ledgers=0;missing=[];noncomplete=[]
    for snapshot in plan.snapshots:
        for binding in (b for b in plan.forecasts if b.checkpoint.origin==snapshot.origin):
            if monotonic()-started>=wall_seconds: raise ValueError('REPLAY_WALL_BUDGET_EXCEEDED')
            key,request,input_digest,snapshot_digest=service.key(snapshot,binding,source)
            run_directory=service.storage.path('runs',key)
            retained=service.storage.load(run_directory,'planning.json')
            label=dict(fixture=snapshot.fixture_id,origin=snapshot.origin,arm=binding.checkpoint.arm)
            if retained is None:
                missing.append(label);continue
            run=ImpactRun.model_validate(retained)
            service.verify_run(run,request,key,input_digest,snapshot_digest)
            if run.status!='COMPLETED' or run.selection is None:
                noncomplete.append(label|dict(status=run.status));continue
            seen=set()
            for strategy in run.selection.comparison.source.strategies:
                candidate=strategy.candidate
                if candidate is not None and candidate.counts not in seen:
                    if evaluate_basket_v2(request,candidate.counts)!=candidate:
                        raise ValueError('FIXED_BASKET_REPLAY_MISMATCH')
                    seen.add(candidate.counts)
            comparison=run.selection.comparison
            if projected(comparison.source)!=(comparison.options,comparison.bindings,comparison.deltas,comparison.diagnostics):
                raise ValueError('COMPARISON_REPLAY_MISMATCH')
            if selection_facts(comparison)!=(run.selection.winner_token,run.selection.eligible_tokens,run.selection.rejected,run.selection.reason):
                raise ValueError('SELECTION_REPLAY_MISMATCH')
            realized=realized_evaluation(data,binding.checkpoint,run.selection)
            retained_realized=RealizedImpact.model_validate(service.storage.load(run_directory,f'realized-{realized.target_digest}.json'))
            if realized!=retained_realized: raise ValueError('REALIZED_REPLAY_MISMATCH')
            count+=1;ledgers+=realized.simulation is not None
    if not count: raise ValueError('NO_COMPLETED_CASES_TO_REPLAY')
    report=dict(status='COMPLETED_CASES_EXACT_REPLAY_VERIFIED',experiment_identity=experiment,
        verified_cases=count,expected_cases=48,complete_primary_ledgers=ledgers,missing=missing,noncomplete=noncomplete,
        procurement_solves=0,wall_seconds=monotonic()-started,wall_budget_seconds=wall_seconds,
        verification_source=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    digest=challenger_digest('impact-verification',report)
    # Keep the basename within Windows path limits in the isolated worktree.
    service.storage.retain(directory,f'verify-{digest}.json',report)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment',required=True)
    args=parser.parse_args()
    report=verify(Path(__file__).resolve().parents[1],args.experiment)
    print(canonical_bytes(report).decode())


if __name__=='__main__': main()
