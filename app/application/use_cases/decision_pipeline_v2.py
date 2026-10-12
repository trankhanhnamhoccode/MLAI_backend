"""Explicit internal /2 integration. No public lifecycle, persistence or default policy."""
from time import perf_counter
from datetime import datetime
from typing import Callable
from app.application.contracts.decision_capture import CaptureProblem
from app.application.contracts.decision_capture_v2 import OperationalPipelineResultV2, PhaseTiming
from app.application.decision_pipeline_v2_validation import pipeline_outcome
from app.application.use_cases.decision_capture import utc_now
from app.application.use_cases.decision_capture_v2 import capture_decision_v2
from app.application.use_cases.bom import expand_bom
from app.application.use_cases.procurement import constraint_coverage
from app.application.use_cases.procurement_v2 import execute_procurement_v2
from app.application.use_cases.procurement_selection import compare_procurement_v2, select_winner
from app.application.contracts.decision_capture_v2 import OperationalDecisionInputV2
from app.application.decision_snapshot_source_v2 import DecisionSnapshotSourceV2
from app.application.procurement_solver_v2 import ProductCandidateSearch


def execute_operational_pipeline_v2(request: OperationalDecisionInputV2, source: DecisionSnapshotSourceV2,
        search_factory: Callable[..., ProductCandidateSearch],
        clock: Callable[[],datetime]=utc_now) -> OperationalPipelineResultV2:
    start=perf_counter();capture=capture_decision_v2(request,source,clock)
    return execute_captured_pipeline_v2(capture,search_factory,perf_counter()-start)


def execute_captured_pipeline_v2(capture, search_factory, capture_preparation_seconds=0.):
    """Pure continuation from retained values; no source reads or persistence."""
    from app.application.contracts.decision_capture_v2 import DecisionCaptureOutcomeV2
    start=perf_counter()
    capture=DecisionCaptureOutcomeV2.model_validate(capture)
    phase={'capture_preparation_seconds':capture_preparation_seconds,'bom_seconds':0.,'engine_seconds':0.,'comparison_seconds':0.,'selector_seconds':0.,'output_revalidation_seconds':0.,'engine_reported_seconds':0.,'engine_overrun_seconds':0.}
    bom=procurement=comparison=selection=None;problems=list(capture.problems)
    if capture.status=='CAPTURED':
        blocked=[c for c in constraint_coverage(capture.procurement_input) if c.status=='BLOCKED']
        if blocked:
            problems.extend(CaptureProblem(code='PROCUREMENT_PREFLIGHT_BLOCKED',kind='DATA_BLOCKER',entity='store',entity_id=capture.request.store_id,field=c.constraint,detail=c.detail) for c in blocked)
        else:
            at=perf_counter();bom=expand_bom(capture.prepared);phase['bom_seconds']=perf_counter()-at
            if bom.status=='COMPLETE' and bom.decision_readiness!='DATA_BLOCKED':
                at=perf_counter()
                procurement=execute_procurement_v2(capture.procurement_input,search_factory)
                phase['engine_seconds']=perf_counter()-at
                phase['engine_reported_seconds']=procurement.elapsed_seconds
                phase['engine_overrun_seconds']=procurement.deadline_overrun_seconds
                # Existing /2 boundaries revalidate their inputs and construct
                # validated outputs. Avoid immediately duplicating the same graph
                # reconstruction here; final pipeline validation remains mandatory.
                at=perf_counter();comparison=compare_procurement_v2(procurement);phase['comparison_seconds']=perf_counter()-at
                at=perf_counter();selection=select_winner(comparison);phase['selector_seconds']=perf_counter()-at
    outcome=pipeline_outcome(capture,bom,procurement,selection)
    body=dict(semantics_version='operational_pipeline/2',capture=capture,outcome=outcome,bom=bom,procurement=procurement,comparison=comparison,selection=selection,problems=tuple(problems))
    # Constructor recursively revalidates the complete output graph (including
    # forged model instances). No model_copy/construct shortcut for business data.
    # Only freshly validated diagnostic timing is amended after this measurement.
    at=perf_counter()
    validated=OperationalPipelineResultV2(**body,timing=PhaseTiming(**phase,total_seconds=perf_counter()-start+capture_preparation_seconds))
    phase['output_revalidation_seconds']=perf_counter()-at
    timing=PhaseTiming(**phase,total_seconds=perf_counter()-start+capture_preparation_seconds)
    # Replacing only diagnostic timing on the already validated result avoids a
    # second expensive graph rebuild; independent cross-phase checks still run.
    object.__setattr__(validated,'timing',timing)
    return validated
