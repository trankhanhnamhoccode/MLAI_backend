"""Portable synthetic E3 corpus; calendar is explicitly fictional, not inferred."""
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

from app.application.contracts.forecast_benchmark import BenchmarkDataset, BenchmarkOrigin, BenchmarkPlan
from app.application.forecast_benchmark_admission import next_run
from app.application.forecast_challenger_serialization import challenger_digest, canonical_bytes


def synthetic_benchmark():
    store=UUID('00000000-0000-0000-0000-000000000001')
    products=tuple({'product_id':UUID(f'00000000-0000-0000-0000-{n:012d}'),'selling_unit':unit}
                   for n,unit in [(11,'cup'),(12,'piece')])
    first,last=date(2025,11,1),date(2026,6,29)
    observations,calendar=[],[]
    known=datetime.combine(first-timedelta(days=7),time.min,tzinfo=ZoneInfo('Asia/Ho_Chi_Minh'))
    for i in range((last-first).days+8):
        day=first+timedelta(days=i)
        closed=i%41==40
        calendar.append({'store_id':store,'day':day,'closed':closed,'holiday':day.day==14,
            'available_at':known,'source':'fictional_owner_operating_calendar/1'})
        if day>last or i%37==6:
            continue
        for code,product in enumerate(products):
            stockout=False if closed else True if i%31==0 else None if i%29==2 else False
            quantity=0 if closed or i%53==5 else 2 if stockout is True else (
                10+2*(i%7)+i//28 if code==0 else 3+(i%5)+i//60)
            observations.append({'store_id':store,'product_id':product['product_id'],
                'sales_date':day,'selling_unit':product['selling_unit'],'quantity':Decimal(quantity),
                'is_stockout':stockout,'available_at':next_run(day,'Asia/Ho_Chi_Minh'),
                'source':'synthetic_formula_raw_sales/1'})
    data=BenchmarkDataset(classification='SYNTHETIC',use_authority='synthetic_fixture:benchmark_setup/1',
        source_revision='synthetic_formula_calendar/1',availability_basis='synthetic_next_run',
        limitations=('Synthetic correctness only; no real demand accuracy, savings or promotion evidence.',
                     'Availability is generated next-run convention; not recovered operational vintages.'),
        store_id=store,timezone='Asia/Ho_Chi_Minh',products=products,observations=observations,calendar=calendar)
    tasks=[]
    for i in range(4):
        day=date(2026,6,1)+timedelta(days=i*7)
        tasks.append(BenchmarkOrigin(origin=day,partition='validation' if i<2 else 'holdout',
            train_end=day-timedelta(days=56),point_start=day-timedelta(days=55),point_end=day-timedelta(days=28),
            calibration_start=day-timedelta(days=27),calibration_end=day))
    plan=BenchmarkPlan(dataset_digest=challenger_digest('dataset',data),tasks=tasks)
    return data,plan


def write_private_inputs(root:Path):
    data,plan=synthetic_benchmark()
    directory=root/'runtime/challenger/benchmarks/inputs'/challenger_digest('dataset',data)
    directory.mkdir(parents=True,exist_ok=True)
    for name,value in [('dataset.json',data),('plan.json',plan)]:
        path=directory/name
        raw=canonical_bytes(value)
        if path.exists() and path.read_bytes()!=raw:
            raise ValueError('Immutable synthetic input conflict')
        if not path.exists():
            path.write_bytes(raw)
    return directory
