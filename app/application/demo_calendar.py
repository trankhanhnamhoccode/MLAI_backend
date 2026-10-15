"""Project only valid sourced fields into an explicitly assumed offline calendar."""
from datetime import timedelta
from app.application.contracts.demo_calendar import DemoCalendarAssumption
from app.application.contracts.demo_workbooks import DemoDataset
from app.application.contracts.forecast_benchmark import BenchmarkDataset
from app.application.contracts.forecast_challenger import CalendarFact
from app.application.forecast_benchmark_admission import next_run
from app.application.forecast_challenger_serialization import challenger_digest

ASSUMED_SOURCE_PREFIX='benchmark_assumed_calendar:'


def assume_calendar(data:BenchmarkDataset,raw:DemoDataset,assumption:DemoCalendarAssumption,
                    calendar_file_sha256:str,*,mode:str='benchmark') -> BenchmarkDataset:
    if mode!='benchmark': raise ValueError('BENCHMARK_CALENDAR_PRODUCTION_REJECTED')
    if (assumption.source_revision!=raw.source_revision or data.source_revision!=raw.source_revision or
        assumption.calendar_file_sha256!=calendar_file_sha256 or
        assumption.calendar_rows_digest!=challenger_digest('demo-calendar-rows',raw.calendar)):
        raise ValueError('CALENDAR_ASSUMPTION_HASH_MISMATCH')
    if (assumption.store_id!=data.store_id or assumption.timezone!=data.timezone or
        set(assumption.product_ids)!={p.product_id for p in data.products}):
        raise ValueError('CALENDAR_ASSUMPTION_SCOPE_MISMATCH')
    if not raw.calendar or len({r.day for r in raw.calendar})!=len(raw.calendar):
        raise ValueError('CALENDAR_ASSUMPTION_DUPLICATE_OR_EMPTY')
    if any(r.closed is None or r.holiday is None or any(s.formula for s in r.sources) for r in raw.calendar):
        raise ValueError('CALENDAR_ASSUMPTION_INVALID_SOURCE')
    calendar={r.day:r for r in raw.calendar}
    if any(o.sales_date in calendar and calendar[o.sales_date].closed and o.quantity>0 for o in data.observations):
        raise ValueError('CALENDAR_ASSUMPTION_SALES_CONFLICT')
    identity=challenger_digest('demo-calendar-assumption',assumption)
    # Synthetic availability belongs only to this detached benchmark projection.
    # Source issue times remain unknown in raw; recorded_at is the actual declaration receipt.
    assumed_at=next_run(min(o.sales_date for o in data.observations)-timedelta(days=1),data.timezone)
    facts=tuple(CalendarFact(store_id=data.store_id,day=r.day,closed=r.closed,holiday=r.holiday,
        available_at=assumed_at,source=ASSUMED_SOURCE_PREFIX+identity) for r in raw.calendar)
    return BenchmarkDataset.model_validate(data.model_dump(mode='python')|dict(calendar=facts,
        limitations=data.limitations+('DEMO_RETROSPECTIVE_ASSUMPTION: sourced closed/holiday only assumed known before feature origins; no historical vintage proof; weather and promotion excluded.',)))
