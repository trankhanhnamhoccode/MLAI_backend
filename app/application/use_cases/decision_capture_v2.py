"""Operational /2 capture; no computation or write while source owns resources."""
from pydantic import ValidationError
from datetime import datetime
from typing import Callable
from app.application.contracts.decision_capture import CaptureProblem
from app.application.contracts.decision_capture_v2 import OperationalDecisionInputV2, OperationalFactsV2, DecisionCaptureOutcomeV2
from app.application.decision_snapshot_source import OperationalDataError
from app.application.decision_capture_v2_validation import project_capture_v2
from app.application.use_cases.decision_capture import utc_now
from app.application.decision_snapshot_source_v2 import DecisionSnapshotSourceV2


def capture_decision_v2(request: OperationalDecisionInputV2,source: DecisionSnapshotSourceV2,
        clock: Callable[[],datetime]=utc_now) -> DecisionCaptureOutcomeV2:
    request=OperationalDecisionInputV2.model_validate(request)
    try:
        wrapped=source.read(request,clock)
    except OperationalDataError as error:
        problems=error.problems
        captured_at=error.captured_at
        wrapped=None
    else:
        captured_at=wrapped.facts.captured_at
        try:wrapped=OperationalFactsV2.model_validate(wrapped.model_dump())
        except ValidationError as error:
            problems=(CaptureProblem(code='INVALID_OPERATIONAL_FACT',kind='DATA_BLOCKER',entity='store',entity_id=request.store_id,field='facts',detail=str(error)),)
            wrapped=None
    if wrapped is None:
        return DecisionCaptureOutcomeV2(semantics_version='operational_capture/2',request=request,captured_at=captured_at,source=None,status='DATA_BLOCKED',operational_basis=None,menu=(),computed_product_ids=(),exclusions=(),override_assessments=(),prepared=None,procurement_input=None,problems=problems,forecast_provenance=None)
    return DecisionCaptureOutcomeV2(semantics_version='operational_capture/2',request=request,captured_at=captured_at,source=wrapped,**project_capture_v2(request,wrapped))
