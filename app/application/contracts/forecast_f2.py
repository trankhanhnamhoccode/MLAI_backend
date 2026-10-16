"""Strict opt-in offline F2 specification; no production/API contract changes."""
from typing import Literal
from pydantic import model_validator
from app.application.contracts.common import Contract


class F2Protocol(Contract):
    protocol_version: Literal['forecast_f2/1']
    parent_experiment: Literal['e8fd6eea4f2528bdd9d83a95b6ffcabc84017228c04f2e347ea5a80ce1524e54']
    closure_policy: Literal['shared_explicit_closure/1']
    endpoint_method: Literal['pooled_horizon_endpoint_residual_nearest_rank/1']
    origins: tuple[Literal['2026-06-10', '2026-06-17', '2026-06-24', '2026-07-01'], ...]
    fit_window: Literal['retained_C_calibration_O-27_through_O_open_known_false_quarantined']
    estimator: Literal['inverse_empirical_CDF_ceil_n_tau_no_interpolation']
    pooling: Literal['horizon_selling_unit_all_five_products']
    minimum_tasks: Literal[30]
    minimum_dates: Literal[7]
    support_fallback: Literal['whole_origin_NOT_FITTED_C1_equals_C0_no_adjustment']
    p50_policy: Literal['preserve_exactly']
    ordering: Literal['lower=max(0,min(p50,raw_lower));upper=max(p50,raw_upper)']
    cqr_policy: Literal['retain_C0_CQR_separate_no_refit_no_relabel']
    selection_rule: Literal['validation_open_endpoint_pinball_strict_improvement_each_endpoint_nonworse_tails_nonworse_no_product_horizon_or_cross_group_regression_ties_C0']
    evaluation_classification: Literal['EXPOSED_DEVELOPMENT_ONLY_NO_FRESH_LABELS']
    wall_seconds: Literal[300]
    maximum_booster_fits: Literal[0]
    maximum_point_cqr_fits: Literal[0]
    maximum_endpoint_fits: Literal[4]
    batches: Literal[1]
    production: Literal['LOCKED']

    # Pydantic Literal integer equality also accepts bool/float; explicitly forbid that coercion.
    @model_validator(mode='before')
    @classmethod
    def strict_budget_and_origins(cls, value):
        expected=('2026-06-10','2026-06-17','2026-06-24','2026-07-01')
        if tuple(value.get('origins',()))!=expected:
            raise ValueError('F2_FROZEN_ORIGINS')
        for name in ('minimum_tasks','minimum_dates','wall_seconds','maximum_booster_fits',
                     'maximum_point_cqr_fits','maximum_endpoint_fits','batches'):
            if type(value.get(name)) is not int:
                raise ValueError('F2_STRICT_COUNTS')
        return value
