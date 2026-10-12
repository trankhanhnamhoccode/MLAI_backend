"""Capture then existing pure engines; no persistence, recommendation or HTTP."""
from datetime import datetime
from typing import Callable

from pydantic import ValidationError

from app.application.contracts.decision_capture import OperationalDecisionInput, OperationalPipelineResult, CaptureProblem
from app.application.contracts.procurement import ProcurementInput, ProcurementBudget
from app.application.contracts.serving import ServingSimulationInput
from app.application.contracts.procurement_comparison import ProcurementComparisonInput
from app.application.decision_snapshot_source import DecisionSnapshotSource
from app.application.procurement_solver import CandidateSearch
from app.application.use_cases.decision_capture import capture_decision, utc_now
from app.application.use_cases.serving import simulate_serving
from app.application.use_cases.procurement import execute_procurement, constraint_coverage
from app.application.use_cases.procurement_comparison import compare_procurement


def execute_operational_pipeline(request: OperationalDecisionInput, source: DecisionSnapshotSource,
                                 search_factory: Callable[..., CandidateSearch],
                                 clock: Callable[[], datetime] = utc_now) -> OperationalPipelineResult:
    capture = capture_decision(request, source, clock)
    if capture.status == 'DATA_BLOCKED':
        return OperationalPipelineResult(capture=capture, status='DATA_BLOCKED')
    prepared = capture.prepared
    config = capture.request.procurement
    budgets = [c for c in prepared.constraints if c.kind == 'BUDGET_LIMIT']
    budget = ProcurementBudget(state='KNOWN', amount=budgets[0].value, currency=prepared.currency,
        provenance=f'DB business_constraints/{budgets[0].id}/v{budgets[0].version}') if budgets else config.budget
    try:
        envelope = ProcurementInput(prepared=prepared, policy=config.policy, offers=config.offers,
            budget=budget, supplier_fees=config.supplier_fees, capacities=config.capacities,
            supplier_limits=config.supplier_limits, arrivals=(), unsupported_configured_constraints=(),
            source_references=tuple(r for r in prepared.source_references if r.entity in
                {'store','forecast_run','product','ingredient','inventory_lot','supplier_term','constraint'}))
    except ValidationError as error:
        # Explicit configuration incompatible with captured facts is a data blocker,
        # not a solver result or technical failure. No solver has been called.
        return OperationalPipelineResult(capture=capture, status='COMPUTATION_BLOCKED', problems=(
            CaptureProblem(code='PROCUREMENT_CONFIGURATION_CONFLICT', kind='DATA_BLOCKER', entity='store',
                entity_id=prepared.request.store_id, field='procurement', detail=str(error)),))
    coverage = constraint_coverage(envelope)
    if any(c.status == 'BLOCKED' for c in coverage):
        return OperationalPipelineResult(capture=capture, status='COMPUTATION_BLOCKED', problems=tuple(
            CaptureProblem(code='PROCUREMENT_PREFLIGHT_BLOCKED', kind='DATA_BLOCKER', entity='store',
                entity_id=prepared.request.store_id, field=c.constraint, detail=c.detail) for c in coverage if c.status == 'BLOCKED'))
    # Existing serving boundary already expands/revalidates BOM first; use that
    # result instead of separately repeating the same expansion here.
    serving = simulate_serving(ServingSimulationInput(prepared=prepared, arrivals=()))
    bom = serving.bom
    if serving.status != 'COMPLETE' or serving.decision_readiness == 'DATA_BLOCKED':
        return OperationalPipelineResult(capture=capture, status='COMPUTATION_BLOCKED', bom=bom, serving=serving)
    procurement = execute_procurement(envelope, search_factory)
    comparison = compare_procurement(ProcurementComparisonInput(procurement=procurement))
    status = 'EXECUTION_ERROR' if procurement.execution == 'ERROR' else (
        'COMPUTATION_BLOCKED' if procurement.execution in ('BLOCKED','NUMERIC_UNSUPPORTED') else 'COMPUTED')
    return OperationalPipelineResult(capture=capture, status=status, bom=bom, serving=serving,
                                     procurement=procurement, comparison=comparison)
