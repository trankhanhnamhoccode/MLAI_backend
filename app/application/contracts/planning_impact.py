"""Offline E4 boundaries: common facts, forecast-only planning, separate realized truth."""
from datetime import date
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, model_validator

from app.application.contracts.common import Contract, Nonblank
from app.application.contracts.forecast_benchmark import ArmCheckpoint
from app.application.contracts.forecast_challenger import Digest
from app.application.contracts.procurement_v2 import ProcurementInputV2
from app.application.contracts.procurement_selection import WinnerSelection
from app.application.contracts.serving import ServingSimulationResult


class ImpactSnapshot(Contract):
    schema_version: Literal[1] = 1
    classification: Literal['COUNTERFACTUAL_SYNTHETIC'] = 'COUNTERFACTUAL_SYNTHETIC'
    fixture_id: Nonblank
    origin: date
    facts_known_at: AwareDatetime
    provenance: Literal['explicit_synthetic_formula_no_actuals/1'] = 'explicit_synthetic_formula_no_actuals/1'
    template: ProcurementInputV2

    @model_validator(mode='after')
    def admitted(self):
        p = self.template.prepared
        if p.request.cutoff_date != self.origin or self.facts_known_at > p.request.order_at:
            raise ValueError('Operational facts must be known at the decision instant')
        if any(v for row in p.forecast.predictions for v in (row.p25, row.p50, row.p75)):
            raise ValueError('Common template contains only explicit placeholder forecasts')
        if p.forecast.model_type != 'counterfactual_placeholder':
            raise ValueError('Template cannot masquerade as a retained model run')
        return self


class ImpactBinding(Contract):
    checkpoint: ArmCheckpoint
    output_digest: Digest


class ImpactPlan(Contract):
    schema_version: Literal[1] = 1
    classification: Literal['COUNTERFACTUAL_SYNTHETIC'] = 'COUNTERFACTUAL_SYNTHETIC'
    e3_experiment: Digest
    dataset_digest: Digest
    protocol_digest: Digest
    snapshots: tuple[ImpactSnapshot, ...]
    forecasts: tuple[ImpactBinding, ...]
    run_order: Literal['origin_fixture_A_B_C/1'] = 'origin_fixture_A_B_C/1'
    repetitions: Literal[1] = 1
    maximum_runs: Annotated[int, Field(strict=True, ge=48, le=48)] = 48
    maximum_native_solves: Annotated[int, Field(strict=True, ge=576, le=576)] = 576
    wall_seconds: Literal[300] = 300
    realized_policy: Literal['complete_horizon_known_false_only/1'] = 'complete_horizon_known_false_only/1'


class RealizedImpact(Contract):
    status: Literal['COMPLETE_PRIMARY_OBSERVED', 'UNAVAILABLE_INCOMPLETE_PRIMARY', 'UNAVAILABLE_NO_WINNER']
    target_digest: Digest
    primary_tasks: int
    total_tasks: int
    simulation: ServingSimulationResult | None


class ImpactRun(Contract):
    identity: Digest
    snapshot_digest: Digest
    forecast_output_digest: Digest
    planning_input_digest: Digest
    binding: ImpactBinding
    snapshot: ImpactSnapshot
    status: Literal['COMPLETED', 'TECHNICAL_FAILURE', 'BUDGET_EXCEEDED']
    reason: Nonblank | None = None
    selection: WinnerSelection | None
    realized: RealizedImpact | None
    elapsed_seconds: Annotated[float, Field(ge=0, allow_inf_nan=False)]
