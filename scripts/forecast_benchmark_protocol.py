"""E1 offline protocol checks only; never imports serving, ORM or the challenger.

JSON here is a development manifest, not a public API. These checks freeze the
experiment and illustrate E2 admission requirements; they do not load a model.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import Enum
import hashlib
import json
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo


class Outcome(str, Enum):
    UNSUPPORTED = "UNSUPPORTED"
    DATA_BLOCKED = "DATA_BLOCKED"
    TECHNICAL_ERROR = "TECHNICAL_ERROR"


class ProtocolError(ValueError):
    def __init__(self, code: str, outcome: Outcome = Outcome.UNSUPPORTED):
        self.code, self.outcome = code, outcome
        super().__init__(code)


@dataclass(frozen=True)
class Task:
    origin: date
    partition: str
    train_end: date
    point_start: date
    point_end: date
    calibration_start: date
    calibration_end: date


REQUIRED_ARTIFACT_FILES = frozenset({
    "model_q25.txt", "model_q50.txt", "model_q75.txt", "feature_schema.json",
    "preprocessing_config.json", "category_mappings.json", "model_metadata.json",
    "point_corrector.json", "calibrator.json", "training_manifest.json",
})
ARMS = (
    ("A_be_baseline_causal_v1", "causal_stockout_v1"),
    ("B_be_lightgbm_causal_v1", "causal_stockout_v1"),
    ("C_engine_native_reconstruction_v1", "engine_native_reconstruction_v1"),
)


def canonical_digest(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(b"shelfcash.forecast-benchmark.e1.v1\n" + encoded).hexdigest()


def _require(condition: bool, code: str,
             outcome: Outcome = Outcome.UNSUPPORTED) -> None:
    if not condition:
        raise ProtocolError(code, outcome)


def _date(value: str) -> date:
    parsed = date.fromisoformat(value)
    _require(parsed.isoformat() == value, "DATE_FORMAT")
    return parsed


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    _require(parsed.tzinfo is not None, "AWARE_TIMESTAMP_REQUIRED")
    return parsed


def _quantity(value: str) -> Decimal:
    _require(isinstance(value, str), "QUANTITY_TEXT_REQUIRED")
    try:
        number = Decimal(value)
    except InvalidOperation as error:
        raise ProtocolError("INVALID_QUANTITY", Outcome.TECHNICAL_ERROR) from error
    _require(number.is_finite() and number >= 0, "NONFINITE_OR_NEGATIVE",
             Outcome.TECHNICAL_ERROR)
    return number


def validate_manifest(manifest: dict[str, Any]) -> tuple[Task, ...]:
    _require(set(manifest) == {
        'schema_version', 'purpose', 'benchmark_enabled', 'promotion_enabled',
        'horizon_days', 'timezone', 'arms', 'comparison', 'selection', 'promotion',
        'availability_assumption', 'tasks', 'freeze_before_scoring', 'purge_rule',
        'arm_configuration',
    }, 'MANIFEST_FIELDS')
    _require(type(manifest["schema_version"]) is int and manifest["schema_version"] == 1,
             "MANIFEST_VERSION")
    _require(manifest["purpose"] == "SYNTHETIC_CORRECTNESS_ONLY" and
             manifest["benchmark_enabled"] is False and
             manifest["promotion_enabled"] is False, "E1_EXECUTION_DISABLED")
    _require(type(manifest["horizon_days"]) is int and manifest["horizon_days"] == 7,
             "HORIZON_UNSUPPORTED")
    ZoneInfo(manifest["timezone"])
    _require(tuple((a["id"], a["reconstruction_policy"]) for a in manifest["arms"]) == ARMS,
             "ARM_SET_CHANGED")
    _require(all(a["fallback"] is False and a["config_ref"] and
                 a["artifact_rule"] for a in manifest["arms"]), "ARM_CONFIGURATION")
    configurations = manifest['arm_configuration']
    _require(set(configurations) == {a[0] for a in ARMS}, 'ARM_CONFIGURATION')
    for arm in manifest['arms']:
        _require(arm['config_sha256'] == canonical_digest(configurations[arm['id']]),
                 'CONFIG_DIGEST_MISMATCH')
    _require(manifest["comparison"] == {
        "scope": "same_store_product_unit", "targets": "paired_common_mask",
        "primary_mask": "observed_known_false", "unknown_mask": "supplementary_observed",
        "stockout_mask": "censored_lower_bound_diagnostics_only",
        "missing_mask": "excluded_reported", "coverage": "all_arms_and_exclusions",
        "outcome_key": "store_product_target_date", "task_key": "store_product_origin_horizon",
    }, "SCORING_MASK_CHANGED")
    _require(manifest["selection"] == {
        "primary_metric": "equal_target_mean_pinball_25_50_75",
        "partition": "validation", "strict_improvement": True,
        "tie_order": [a[0] for a in ARMS], "holdout_tuning": False,
    }, "SELECTION_CHANGED")
    _require(manifest["promotion"] == {
        "automatic": False, "minimum_origins_per_partition": 2,
        "minimum_distinct_outcomes_per_partition": 28,
        "real_unseen_data_required": True, "point_in_time_evidence_or_explicit_limitation": True,
        "validation_and_holdout_strictly_better_than_A_and_B": True,
        "complete_requested_output": True, "paired_coverage_fraction": 1,
        "final_nonfinite_count": 0, "final_crossing_count": 0,
        "replay_digest_match": True, "planning_acceptance_required": True,
        "user_activation_required": True,
    }, "PROMOTION_CHANGED")
    _require(manifest["availability_assumption"] == "synthetic_explicit_known_at",
             "AVAILABILITY_ASSUMPTION")
    tasks = tuple(Task(_date(t["origin"]), t["partition"], _date(t["train_end"]),
                       _date(t["point_start"]), _date(t["point_end"]),
                       _date(t["calibration_start"]), _date(t["calibration_end"]))
                  for t in manifest["tasks"])
    _require(len({t.origin for t in tasks}) == len(tasks) and
             list(tasks) == sorted(tasks, key=lambda t: t.origin), "ORIGIN_ORDER")
    for task in tasks:
        _require(task.partition in {"validation", "holdout"}, "PARTITION")
        _require(task.train_end < task.point_start <= task.point_end <
                 task.calibration_start <= task.calibration_end <= task.origin,
                 "WINDOW_LEAKAGE")
    for previous, following in zip(tasks, tasks[1:]):
        _require(previous.origin + timedelta(days=7) <= following.origin,
                 "TARGET_WINDOW_OVERLAP")
    validation = [t for t in tasks if t.partition == "validation"]
    holdout = [t for t in tasks if t.partition == "holdout"]
    _require(len(validation) >= 2 and len(holdout) >= 2, "INSUFFICIENT_ORIGINS")
    _require(max(t.origin for t in validation) < min(t.origin for t in holdout),
             "PARTITION_ORDER")
    _require(manifest["freeze_before_scoring"] is True and
             manifest["purge_rule"] == "fit_labels_known_before_prediction_origin",
             "PROTOCOL_NOT_FROZEN")
    return tasks


def validate_case(case: dict[str, Any]) -> None:
    """Validate a synthetic detached admission/output example, without inference."""
    _require(set(case) == {
        'cutoff', 'history_start', 'horizon', 'timezone', 'origin_available_at',
        'quantity_basis', 'store_id', 'products', 'observations', 'calendar',
        'artifact', 'mode', 'predictions',
    }, 'CASE_FIELDS')
    cutoff = _date(case["cutoff"])
    start = _date(case["history_start"])
    _require(start <= cutoff, "HISTORY_WINDOW")
    _require(type(case["horizon"]) is int and case["horizon"] == 7, "HORIZON_UNSUPPORTED")
    ZoneInfo(case["timezone"])
    instant = _instant(case["origin_available_at"])
    _require(instant.astimezone(ZoneInfo(case["timezone"])).date() == cutoff + timedelta(days=1),
             "ORIGIN_AVAILABILITY_BOUNDARY")
    _require(case["quantity_basis"] == "canonical_observed_sales", "DOUBLE_RECONSTRUCTION")
    store = case["store_id"]
    _require(str(UUID(store)) == store, "STORE_ID")
    products = {p["id"]: p["unit"] for p in case["products"]}
    _require(products and len(products) == len(case["products"]), "PRODUCT_SCOPE")
    _require(all(str(UUID(p)) == p and unit.strip() == unit and unit
                 for p, unit in products.items()), "PRODUCT_ID_UNIT")
    seen = set()
    for row in case["observations"]:
        _require(row["store_id"] == store and row["product_id"] in products, "FOREIGN_SCOPE")
        _require(row["unit"] == products[row["product_id"]], "UNIT_MISMATCH")
        day = _date(row["date"])
        _require(start <= day <= cutoff, "OBSERVATION_OUTSIDE_WINDOW")
        _require(_instant(row["known_at"]) <= instant, "FUTURE_LABEL", Outcome.DATA_BLOCKED)
        _quantity(row["quantity"])
        _require(row["stockout"] is None or type(row["stockout"]) is bool, "STOCKOUT_TYPE")
        key = row["product_id"], day
        _require(key not in seen, "DUPLICATE_OBSERVATION")
        seen.add(key)
    _require({pid for pid, _ in seen} == set(products), "PRODUCT_HISTORY_MISSING",
             Outcome.DATA_BLOCKED)
    calendar = {}
    for row in case["calendar"]:
        day = _date(row["date"])
        _require(row["store_id"] == store, "FOREIGN_CALENDAR")
        _require(day not in calendar, "DUPLICATE_CALENDAR")
        _require(type(row["closed"]) is bool and type(row["holiday"]) is bool and
                 bool(row["source"]), "CALENDAR_FACTS_REQUIRED", Outcome.DATA_BLOCKED)
        _require(_instant(row["known_at"]) <= instant, "FUTURE_CALENDAR", Outcome.DATA_BLOCKED)
        weather = row["weather"]
        if weather is not None:
            _require(weather["kind"] == "forecast" and
                     _instant(weather["issued_at"]) <= instant and
                     _instant(weather["available_at"]) <= instant,
                     "UNSAFE_WEATHER", Outcome.DATA_BLOCKED)
        calendar[day] = row
    dates = {cutoff + timedelta(days=h) for h in range(1, 8)}
    # The engine fills a dense historical panel from the first observation.
    panel_start = min(day for _, day in seen)
    required_days = {panel_start + timedelta(days=i)
                     for i in range((cutoff + timedelta(days=7) - panel_start).days + 1)}
    _require(required_days <= set(calendar), "CALENDAR_COVERAGE_MISSING", Outcome.DATA_BLOCKED)
    for row in case["observations"]:
        _require(not calendar[_date(row["date"])]["closed"] or _quantity(row["quantity"]) == 0,
                 "CLOSED_DAY_OBSERVATION_CONFLICT", Outcome.DATA_BLOCKED)
    artifact = case["artifact"]
    files = artifact["files"]
    _require(REQUIRED_ARTIFACT_FILES <= set(files), "ARTIFACT_MISSING", Outcome.TECHNICAL_ERROR)
    checksums = artifact["checksums"]
    _require(set(files) == set(checksums), "CHECKSUM_COVERAGE", Outcome.TECHNICAL_ERROR)
    for name, content in files.items():
        _require(name in REQUIRED_ARTIFACT_FILES, "ARTIFACT_PATH", Outcome.TECHNICAL_ERROR)
        _require(hashlib.sha256(content.encode()).hexdigest() == checksums[name],
                 "ARTIFACT_CORRUPT", Outcome.TECHNICAL_ERROR)
    _require(artifact["schema"] == "3.0" and
             artifact["cqr_semantics"] == "cqr-order-statistic-v2" and
             artifact["point_semantics"] == "additive-median-residual-v1", "ARTIFACT_INCOMPATIBLE")
    for field in ("training_label_cutoff", "point_fit_label_cutoff", "calibration_label_cutoff"):
        _require(_date(artifact[field]) <= cutoff, "ARTIFACT_FUTURE_LABEL", Outcome.DATA_BLOCKED)
    _require(_instant(artifact["available_at"]) <= instant,
             "ARTIFACT_NOT_AVAILABLE", Outcome.DATA_BLOCKED)
    _require(artifact["scope"] == {"store_id": store, "products": case["products"],
                                    "timezone": case["timezone"]}, "ARTIFACT_SCOPE")
    _require(case["mode"] in {"synthetic_offline", "production"}, "EXECUTION_MODE")
    if case["mode"] == "production":
        _require(artifact["promotion_status"] == "promoted" and
                 artifact["production_available_at"] is not None,
                 "ARTIFACT_NOT_PROMOTED", Outcome.DATA_BLOCKED)
        _require(_instant(artifact["production_available_at"]) <= instant,
                 "ARTIFACT_NOT_AVAILABLE", Outcome.DATA_BLOCKED)
    output = set()
    for row in case["predictions"]:
        _require(row["store_id"] == store and row["product_id"] in products, "FOREIGN_SCOPE")
        _require(row["unit"] == products[row["product_id"]], "UNIT_MISMATCH")
        day = _date(row["date"])
        _require(day in dates and row["horizon"] == (day - cutoff).days, "OUTPUT_HORIZON")
        values = tuple(_quantity(row[q]) for q in ("p25", "p50", "p75"))
        _require(values[0] <= values[1] <= values[2], "FINAL_QUANTILE_CROSSING",
                 Outcome.TECHNICAL_ERROR)
        lower, upper = _quantity(row["interval_lower"]), _quantity(row["interval_upper"])
        _require(lower <= values[1] <= upper, "INVALID_CQR_INTERVAL", Outcome.TECHNICAL_ERROR)
        if calendar[day]["closed"]:
            _require(values == (0, 0, 0) and lower == upper == 0, "CLOSED_DAY_NOT_ZERO",
                     Outcome.TECHNICAL_ERROR)
        key = row["product_id"], day
        _require(key not in output, "DUPLICATE_OUTPUT", Outcome.TECHNICAL_ERROR)
        output.add(key)
    _require(output == {(pid, day) for pid in products for day in dates},
             "OUTPUT_COVERAGE", Outcome.TECHNICAL_ERROR)


def materialize_fixture(base: dict[str, Any], changes: list[dict[str, Any]]) -> dict[str, Any]:
    """Explicit path replacements in portable fixtures; originals stay immutable."""
    from copy import deepcopy
    case = deepcopy(base)
    for change in changes:
        parent = case
        for key in change["path"][:-1]:
            parent = parent[key]
        parent[change["path"][-1]] = deepcopy(change["value"])
    return case
