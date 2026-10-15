"""F3 opt-in counterfactual benchmark boundaries; legacy E4 contracts unchanged."""
from typing import Literal,Annotated
from datetime import date
from pydantic import Field,model_validator
from app.application.contracts.common import Contract
from app.application.contracts.forecast_challenger import Digest
from app.application.contracts.planning_impact import ImpactBinding,ImpactSnapshot,ImpactRun

Variant=Literal['B_COMMON','C0_COMMON','C1_COMMON']


class F3Binding(Contract):
    variant: Variant
    forecast: ImpactBinding
    f2_identity: Digest
    endpoint_parameters_sha256: Digest | None


class F3Plan(Contract):
    version: Literal['planning_f3/1']='planning_f3/1'
    classification: Literal['F3_SYNTHETIC']='F3_SYNTHETIC'
    f2_identity: Digest
    origin_rule: Literal['latest_two_F2_origins_chronological_no_impact_scores']='latest_two_F2_origins_chronological_no_impact_scores'
    origins: tuple[date,...]
    snapshots: tuple[ImpactSnapshot,...]
    forecasts: tuple[F3Binding,...]
    run_order: tuple[tuple[date,str,Variant],...]
    wall_seconds: Literal[300]=300
    maximum_runs: Annotated[int,Field(strict=True,ge=24,le=24)]=24
    maximum_native_solves: Annotated[int,Field(strict=True,ge=144,le=144)]=144
    per_run_seconds: Literal['4']='4'
    maximum_solves_per_strategy: Literal[2]=2
    certification_vector_limit: Literal[9]=9
    seed_policy: Literal['unchanged_host_scipy_highs_default_no_exposed_seed']='unchanged_host_scipy_highs_default_no_exposed_seed'
    main_comparison: Literal['B_COMMON_vs_C0_COMMON']='B_COMMON_vs_C0_COMMON'
    c1_role: Literal['exploratory_sensitivity_not_selected_no_impact_selection']='exploratory_sensitivity_not_selected_no_impact_selection'
    realized_policy: Literal['complete_horizon_known_false_only/1']='complete_horizon_known_false_only/1'
    @model_validator(mode='after')
    def scope(self):
        if len(self.origins)!=2 or tuple(sorted(set(self.origins)))!=self.origins or len(self.snapshots)!=8 or len(self.forecasts)!=6:
            raise ValueError('F3_FROZEN_POPULATION')
        variants={'B_COMMON','C0_COMMON','C1_COMMON'}
        if {(b.forecast.checkpoint.origin,b.variant) for b in self.forecasts}!={(o,a) for o in self.origins for a in variants}:
            raise ValueError('F3_FORECAST_BINDINGS')
        expected={(s.origin,s.fixture_id,a) for s in self.snapshots for a in variants}
        if len(expected)!=24 or set(self.run_order)!=expected or len(self.run_order)!=24:raise ValueError('F3_RUN_ORDER')
        if any(s.template.policy.computation_seconds!=4 or s.template.policy.max_solves_per_strategy!=2
               or s.template.policy.certification_vector_limit not in (0,9) for s in self.snapshots):
            raise ValueError('F3_SEARCH_LIMITS')
        return self


class F3Run(ImpactRun):
    variant: Variant
    f2_identity: Digest
