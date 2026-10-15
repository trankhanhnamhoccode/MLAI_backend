"""Projection of an already verified retained pair; no IO or business execution."""
from uuid import UUID

from app.application.contracts.decision_evidence import (
    DecisionEvidence, EvidenceIdentity, EvidenceOverview, IngredientIdentity,
    OptionIdentity, references_for,
)
from app.application.contracts.planning_public import RunView
from app.application.contracts.planning_run import PlanningRunRecord
from app.application.planning_inspection_projection import terminal, select, explanation, ingredient_detail, label


def project_evidence(record: PlanningRunRecord, view: RunView, *, option_id: str | None = None,
                     ingredient_id: UUID | None = None) -> DecisionEvidence:
    """Trusted verified-reader input only; never accept records from HTTP clients.

    Overview excludes option payloads. Ingredient/detail is requested explicitly;
    a retained winner is used only for explicit Ingredient context without an option.
    """
    terminal(record)
    if (record.run_id, record.store_id, record.status, record.outcome) != (view.run_id, view.store_id, view.status, view.outcome):
        raise ValueError('Verified record/view identity mismatch')
    selected = select(view, option_id)[0] if option_id is not None or ingredient_id is not None else None
    detail = ingredient_detail(record, view, ingredient_id, option_id) if ingredient_id is not None else None
    prepared = record.capture.prepared if record.capture else None
    result = view.result
    identity = EvidenceIdentity(run_id=record.run_id, store_id=record.store_id,
        aggregate_digest=view.response_version, input_digest=record.input_digest,
        result_digest=record.result_digest, request_digest=record.request_digest, storage_version=record.storage_version,
        package_schema_version=record.package_schema_version,
        result_schema_version=record.result.semantics_version if record.result else None,
        capture_schema_version=record.capture.semantics_version if record.capture else None,
        accepted_at=record.accepted_at, started_at=view.started_at, finished_at=view.finished_at,
        captured_at=record.capture.captured_at if record.capture else None)
    overview = EvidenceOverview(status=view.status, outcome=view.outcome,
        recommendation_available=view.outcome == 'recommendation_available', request=view.request,
        configuration=view.configuration, temporal_basis=view.operational_basis, scope=view.scope,
        ingredients=tuple(IngredientIdentity(ingredient_id=i.ingredient_id, unit=i.unit,
            name=label(record, i.ingredient_id)[0], name_availability=label(record, i.ingredient_id)[1])
            for i in prepared.ingredients) if prepared else (),
        forecast=view.forecast, execution=view.execution, strategies=result.strategies if result else (),
        selection_proof=record.result.selection.proof if record.result and record.result.selection else None,
        source_references=prepared.source_references if prepared else (),
        options=tuple(OptionIdentity(option_id=o.option_id, source_strategies=o.source_strategies,
            eligible=o.eligible) for o in result.options) if result else (),
        explanation=explanation(record, view, None), assumptions=prepared.assumptions if prepared else (),
        omissions=('ZERO_PURCHASE_BASELINE_NOT_PROJECTED', 'ACTUAL_OUTCOMES_NOT_CAPTURED',
                   'PROBABILITIES_PROFIT_CAUSALITY_NOT_CAPTURED',
                   *(("COMPUTED_SCOPE_NOT_AVAILABLE",) if prepared is None else ()),
                   *(("OPTION_DETAIL_NOT_REQUESTED",) if selected is None else ())))
    return DecisionEvidence(identity=identity, overview=overview, option=selected, ingredient=detail,
        references=references_for(identity, overview, selected, detail))
