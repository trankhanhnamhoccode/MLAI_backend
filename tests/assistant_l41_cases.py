"""Synthetic20/35 factory through capture/exact engine and real persistence primitives.

Only operational supplier input changes; no output quantity patch or construct bypass.
"""
from decimal import Decimal
from uuid import uuid4
from scripts.planning_verification_cases import small_case
from scripts.decision_capture_v2_demo_cases import SyntheticSnapshotSourceV2
from app.application.contracts.decision_capture_v2 import OperationalFactsV2
from app.application.use_cases.planning_setup import resolve_planning_setup
from app.application.use_cases.planning_pipeline import prepare_planning_pipeline
from app.application.use_cases.decision_capture_v2 import capture_decision_v2
from app.application.use_cases.decision_pipeline_v2 import execute_captured_pipeline_v2
from app.application.use_cases.planning_run import PlanningRunUseCases
from app.infrastructure.procurement_milp_v2 import NativeProductSearch
from tests.assistant_cases import realistic_record


def milk_inputs(kind='milk'):
    request,config,declarations,facts=small_case('purchase')
    data=facts.model_dump()
    # Demand20g, min95%=19g; pack17.5g needs TWO packs =>35g.
    # Fresh milk pack10g similarly needs TWO packs =>20g. Cost/budget unchanged.
    data['facts']['supplier_terms'][1]['pack_size_base_quantity']=Decimal('17.5')
    if kind in ('mixed','failed'):
        for point in data['facts']['forecast']['predictions']:
            point['p25']/=2
            point['p75']*=2
    if kind=='mixed':
        # Explicit synthetic BASE40 allows LEAN one-pack basket; BASE/HIGH
        # construction still use two. LOW saturates both, other paths differ.
        request={'requirements_mode':'custom','forecast_start_date':request['forecast_start_date'],
            'requirements':{'paths':[{'path':'BASE','min_fill_rate_percent':'40','product_overrides':[]}],'budget_limit':'10'}}
    facts=OperationalFactsV2.model_validate(data)
    outcome=resolve_planning_setup(request,config)
    assert outcome.status=='RESOLVED',outcome
    resolution=outcome.resolution
    source=SyntheticSnapshotSourceV2(facts)
    return request,resolution,declarations,source


def create_milk_run(engine,actor_id,kind='milk'):
    request,resolution,declarations,source=milk_inputs(kind)
    # Public metadata is hand-authored synthetic source labels, not result facts.
    # Same forecast/Store scope as small_case and existing assistant fixture.
    metadata=realistic_record(actor_id=actor_id)
    at=source.facts.facts.captured_at
    service=PlanningRunUseCases(engine,clock=lambda:at)
    accepted=service.accept(actor_id,resolution.configuration.store_id,str(uuid4()),request,resolution,
        public_metadata=lambda session,resolved:metadata.public_acceptance)
    claimed=service.claim(accepted.store_id,accepted.run_id)
    capture=capture_decision_v2(prepare_planning_pipeline(resolution,declarations),source,lambda:at)
    retained=service.retain(claimed.store_id,claimed.run_id,claimed.claim,declarations,capture,public_capture=metadata.public_capture)
    class PartialSearch(NativeProductSearch):
        def solve(self,strategy,phase,deadline):
            if strategy=='PROTECTED':raise ValueError('SYNTHETIC injected protected search failure')
            return super().solve(strategy,phase,deadline)
    result=execute_captured_pipeline_v2(retained.capture,PartialSearch if kind=='failed' else NativeProductSearch)
    final=service.finalize(claimed.store_id,claimed.run_id,claimed.claim,result)
    # Full aggregate validation performed by finalize and a fresh owned read.
    reread=service.read(final.store_id,final.run_id).record
    assert reread==final and final.status==('failed' if kind=='failed' else 'completed')
    from app.application.planning_public_projection import project_run
    from tests.assistant_cases import row_for
    view=project_run(final,response_version=row_for(final).record_digest)
    winner=next(o for o in view.result.options if o.option_id==view.result.winner_option_id)
    amounts={str(p.ingredient_id):p.quantity.decimal_view for p in winner.purchases}
    if kind=='milk':assert sorted(amounts.values())==['20','35'],amounts
    return final
