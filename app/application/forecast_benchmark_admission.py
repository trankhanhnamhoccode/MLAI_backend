"""Causal eligibility and frozen experiment policy; no filesystem/model imports."""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.application.contracts.forecast_benchmark import ARMS, PROTOCOL_DIGEST, BenchmarkDataset, BenchmarkPlan
from app.application.contracts.forecast_challenger import ChallengerFailure as Failure
from app.application.forecast_challenger_serialization import challenger_digest
from app.application.forecast_challenger_validation import require
from app.domain.forecasting.validation import validate_prepared_input


def next_run(day: date, timezone: str) -> datetime:
    return datetime.combine(day + timedelta(days=1), time.min, tzinfo=ZoneInfo(timezone))


def holdout_dates(plan: BenchmarkPlan) -> frozenset[date]:
    return frozenset(t.origin + timedelta(days=h) for t in plan.tasks if t.partition == 'holdout' for h in range(1, 8))


def admit_dataset(data: BenchmarkDataset) -> None:
    require(bool(data.observations), 'DATASET_EMPTY', Failure.DATA_BLOCKED)
    first, last = min(o.sales_date for o in data.observations), max(o.sales_date for o in data.observations)
    validate_prepared_input(data.store_id, tuple(p.product_id for p in data.products), first, last,
        tuple((p.product_id, p.selling_unit) for p in data.products),
        tuple((o.store_id, o.product_id, o.sales_date, o.quantity, o.selling_unit) for o in data.observations),
        tuple(last+timedelta(days=h) for h in range(1, 8)))
    require(all(o.available_at >= next_run(o.sales_date, data.timezone) for o in data.observations),
            'LABEL_AVAILABILITY_BEFORE_DAY_CLOSED', Failure.DATA_BLOCKED)
    require(len({c.day for c in data.calendar}) == len(data.calendar) and
            all(c.store_id == data.store_id for c in data.calendar), 'CALENDAR_SCOPE_OR_DUPLICATE')
    if data.availability_basis != 'historical_vintages':
        require(bool(data.limitations), 'AVAILABILITY_LIMITATION_REQUIRED')
    require(data.classification == 'SYNTHETIC' or data.use_authority.startswith('user_authorized:'),
            'DATA_USE_AUTHORITY_REQUIRED', Failure.DATA_BLOCKED)


def admit_plan(data: BenchmarkDataset, plan: BenchmarkPlan) -> None:
    admit_dataset(data)
    require(plan.protocol_digest == PROTOCOL_DIGEST and plan.configuration_ids == ARMS,
            'FROZEN_PROTOCOL_OR_ARMS_CHANGED')
    require(plan.dataset_digest == challenger_digest('dataset', data), 'DATASET_DIGEST_MISMATCH')
    require(len(plan.tasks) == 4 and [t.partition for t in plan.tasks] == ['validation']*2+['holdout']*2,
            'FROZEN_PARTITIONS')
    for index, task in enumerate(plan.tasks):
        require((task.train_end, task.point_start, task.point_end, task.calibration_start, task.calibration_end) == (
            task.origin-timedelta(days=56), task.origin-timedelta(days=55), task.origin-timedelta(days=28),
            task.origin-timedelta(days=27), task.origin), 'FROZEN_WINDOWS')
        if index:
            require(task.origin-plan.tasks[index-1].origin == timedelta(days=7), 'FROZEN_ORIGIN_SPACING')


def at_origin(data: BenchmarkDataset, origin: date):
    instant = next_run(origin, data.timezone)
    return tuple(o for o in data.observations if o.sales_date <= origin and o.available_at <= instant)


def calendar_at_origin(data: BenchmarkDataset, origin: date):
    instant = next_run(origin, data.timezone)
    rows = at_origin(data, origin)
    require(rows, 'PRODUCT_HISTORY_MISSING', Failure.DATA_BLOCKED)
    first = min(o.sales_date for o in rows)
    required = {first+timedelta(days=i) for i in range((origin+timedelta(days=7)-first).days+1)}
    calendar = tuple(c for c in data.calendar if c.day in required and c.available_at <= instant)
    require({c.day for c in calendar} == required, 'SOURCED_CALENDAR_NOT_AVAILABLE', Failure.DATA_BLOCKED)
    return calendar
