"""Frozen hand fixture adapters, not a second production solver."""
from scripts.planning_verification_cases import small_case
from scripts.decision_capture_v2_demo_cases import SyntheticSnapshotSourceV2
from app.application.contracts.decision_capture_v2 import OperationalFactsV2
from app.application.use_cases.planning_setup import resolve_planning_setup
from app.application.use_cases.planning_pipeline import PlanningPipelineDeclarations, prepare_planning_pipeline
from app.application.use_cases.decision_capture_v2 import capture_decision_v2
from app.application.use_cases.decision_pipeline_v2 import execute_captured_pipeline_v2
from app.infrastructure.procurement_milp_v2 import NativeProductSearch
from app.application.procurement_solver import NumericUnsupported


def case(kind='stock'):
    request,config,declarations,facts = small_case('stock' if kind in {'partial','blocked','empty','numeric'} else kind)
    factory = NativeProductSearch
    if kind in {'partial','numeric'}:
        body = facts.model_dump()
        for point in body['facts']['forecast']['predictions']:
            point['p75'] *= 2
        facts = OperationalFactsV2.model_validate(body)
        def factory(*args):
            if kind=='numeric':
                raise NumericUnsupported('INJECTED projection limit')
            raise ValueError('INJECTED search programming failure')
    if kind in {'blocked','empty'}:
        body = declarations.model_dump()
        if kind=='blocked':
            body['payable_fee_coverage']='UNKNOWN'
        else:
            for row in body['inventory_scope']:
                row['state']='UNKNOWN'
        declarations = PlanningPipelineDeclarations.model_validate(body)
    resolution = resolve_planning_setup(request,config).resolution
    source = SyntheticSnapshotSourceV2(facts)
    return request,resolution,declarations,source,factory


def computation(kind='stock'):
    request,resolution,declarations,source,factory = case(kind)
    capture = capture_decision_v2(prepare_planning_pipeline(resolution,declarations),source,
                                 lambda:source.facts.facts.captured_at)
    result = execute_captured_pipeline_v2(capture,factory)
    return request,resolution,declarations,capture,result
