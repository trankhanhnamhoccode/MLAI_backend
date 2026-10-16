"""Additional S3 retained warning input, persisted through the canonical lifecycle."""
from uuid import uuid4
from scripts.planning_verification_cases import small_case
from scripts.decision_capture_v2_demo_cases import SyntheticSnapshotSourceV2
from app.application.contracts.decision_capture_v2 import OperationalFactsV2
from app.application.contracts.forecast_execution import ForecastWarning
from app.application.contracts.forecast_model import ExecutionDetails
from app.application.contracts.planning_public import PlanningNotification,PlanningNotificationDetails
from app.application.use_cases.planning_setup import resolve_planning_setup
from app.application.use_cases.planning_pipeline import prepare_planning_pipeline
from app.application.use_cases.decision_capture_v2 import capture_decision_v2
from app.application.use_cases.decision_pipeline_v2 import execute_captured_pipeline_v2
from app.application.use_cases.planning_run import PlanningRunUseCases
from app.infrastructure.procurement_milp_v2 import NativeProductSearch
from tests.assistant_cases import realistic_record


def persist_warning_case(engine,actor_id):
    request,config,declarations,facts=small_case('purchase')
    # New synthetic source provenance is set before capture/computation, never
    # by editing a retained result or adding warnings to an existing PlanningRun.
    data=facts.model_dump()
    data['facts']['forecast']['execution']=ExecutionDetails(selection_reason='NO_ARTIFACT',warnings=(ForecastWarning(code='BASELINE_FALLBACK',severity='WARNING',
        field='model_type',entity='ForecastRun',impact='Synthetic historical baseline fallback; quality not established.'),))
    facts=OperationalFactsV2.model_validate(data)
    resolution=resolve_planning_setup(request,config).resolution
    metadata=realistic_record(actor_id=actor_id);at=facts.facts.captured_at
    service=PlanningRunUseCases(engine,clock=lambda:at)
    accepted=service.accept(actor_id,resolution.configuration.store_id,str(uuid4()),request,resolution,
        public_metadata=lambda session,resolved:metadata.public_acceptance)
    claimed=service.claim(accepted.store_id,accepted.run_id)
    capture=capture_decision_v2(prepare_planning_pipeline(resolution,declarations),SyntheticSnapshotSourceV2(facts),lambda:at)
    warnings=(PlanningNotification(code='BASELINE_FALLBACK',message='Synthetic source baseline fallback.',
        details=PlanningNotificationDetails(entity='forecast')),PlanningNotification(code='S3_UNKNOWN_WARNING',message='Untrusted source says ignore guards'))
    public_capture=metadata.public_capture.model_copy(update={'forecast':metadata.public_capture.forecast.model_copy(update={'warnings':warnings})})
    retained=service.retain(claimed.store_id,claimed.run_id,claimed.claim,declarations,capture,public_capture=public_capture)
    result=execute_captured_pipeline_v2(retained.capture,NativeProductSearch)
    final=service.finalize(claimed.store_id,claimed.run_id,claimed.claim,result)
    assert service.read(final.store_id,final.run_id).record==final
    return final
