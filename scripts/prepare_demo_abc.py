"""Hash-bound calendar declaration and exact native support inspection, with zero fits."""
import argparse
from collections import Counter
from datetime import datetime,timedelta,timezone
import hashlib
from pathlib import Path

from app.application.contracts.demo_calendar import DemoCalendarAssumption
from app.application.contracts.demo_workbooks import DemoDataset
from app.application.contracts.forecast_benchmark import ARMS,BenchmarkDataset,BenchmarkPlan,BenchmarkOrigin,BenchmarkBudget
from app.application.demo_calendar import assume_calendar
from app.application.forecast_benchmark_admission import at_origin,holdout_dates,next_run
from app.application.forecast_challenger_serialization import challenger_digest,canonical_bytes
from app.application.use_cases.forecast_benchmark import load_protocol
from app.infrastructure.forecast_benchmark_features import NativeFrameCache,build_native_training_table
from app.infrastructure.forecast_benchmark_storage import BenchmarkStorage,FitBudget

ROOT=Path(__file__).resolve().parents[1]
BASE='571fb650d4a867e7e8e51e485fc83b960dc5c1dd4aa52ab260d9a924c67ad21d'


def inputs(root:Path):
    source=root/'runtime/challenger/dataset-admission/datasets'/BASE
    storage=BenchmarkStorage(source)
    raw=DemoDataset.model_validate(storage.load(source,'normalized.json'))
    data=BenchmarkDataset.model_validate(storage.load(source,'dataset.json'))
    plan=BenchmarkPlan.model_validate(storage.load(source,'plan.json'))
    sources=storage.load(source,'sources.json')
    for row in sources:
        for name in (row['path'],*row['aliases']):
            if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=row['sha256']: raise ValueError('RAW_WORKBOOK_CHANGED')
    calendar=next(row['sha256'] for row in sources if row['role']=='calendar')
    store=BenchmarkStorage(root/'runtime/challenger/demo-abc')
    key=challenger_digest('calendar-assumption-scope',dict(source=raw.source_revision,calendar=calendar,
        rows=raw.calendar,scope=data.products,timezone=data.timezone))
    directory=store.path('inputs',key)
    old=store.load(directory,'calendar-assumption.json')
    declaration=DemoCalendarAssumption.model_validate(old) if old else DemoCalendarAssumption(
        source_revision=raw.source_revision,calendar_file_sha256=calendar,
        calendar_rows_digest=challenger_digest('demo-calendar-rows',raw.calendar),store_id=data.store_id,
        product_ids=tuple(p.product_id for p in data.products),timezone=data.timezone,recorded_at=datetime.now(timezone.utc))
    projected=assume_calendar(data,raw,declaration,calendar)
    store.retain(directory,'calendar-assumption.json',declaration)
    store.retain(directory,'sources.json',sources)
    store.retain(directory,'dataset.json',projected)
    return store,directory,projected,plan,declaration


def post_support(data,task,start,end,fit_available,plan,config,guard):
    actuals={(str(o.product_id),o.sales_date):o for o in data.observations}
    forbidden=holdout_dates(plan)
    counts=Counter();dates={};exclusions=Counter()
    for ordinal in range((start-timedelta(days=7)).toordinal(),end.toordinal()):
        guard.check()
        origin=start.fromordinal(ordinal)
        if origin<fit_available:
            exclusions['purged_before_fit_available']+=sum(start<=origin+timedelta(days=h)<=end for h in range(1,8))*len(data.products)
            continue
        _,frame=guard.native_cache.get(data,origin,config)
        for row in frame.itertuples(index=False):
            target=row.target_date.date()
            if not start<=target<=end: continue
            if target in forbidden: exclusions['holdout_quarantined']+=1;continue
            actual=actuals.get((str(row.product_key),target))
            if actual is None or actual.is_stockout is not False or actual.available_at>next_run(end,data.timezone):
                exclusions['missing_censored_unknown_unavailable']+=1;continue
            key=(str(row.product_key),int(row.horizon))
            counts[key]+=1;dates.setdefault(key,set()).add(target)
    return dict(total_tasks=sum(counts.values()),by_product_horizon=[dict(product=p,horizon=h,tasks=n,distinct_dates=len(dates[p,h]))
        for (p,h),n in sorted(counts.items())],minimum_horizon_tasks=min((sum(n for (p,h),n in counts.items() if h==i) for i in range(1,8)),default=0),
        minimum_horizon_dates=min((len(set().union(*(v for (p,h),v in dates.items() if h==i))) for i in range(1,8)),default=0),exclusions=dict(exclusions))


def inspect(root:Path):
    from shelfcash_forecast.config import ForecastConfig
    from shelfcash_forecast.features.specification import CategoryEncoder
    store,directory,data,old,declaration=inputs(root)
    spec=load_protocol(root)['arm_configuration'][ARMS[2]]
    config=ForecastConfig.from_dict(spec['forecast_config'])
    encoder=CategoryEncoder({'store_key':{str(data.store_id):0},'product_key':{str(p.product_id):i for i,p in enumerate(data.products)}})
    guard=FitBudget(BenchmarkBudget(),native_cache=NativeFrameCache())
    rows=[]
    for task in old.tasks:
        # Inspect original and proposed cuts using identical native code, no fits/predictions.
        candidates=[]
        for label,lag in (('old_56_day',56),('proposed_48_day',48)):
            cut=task.origin-timedelta(days=lag)
            table,excluded=build_native_training_table(data,cut,old,config,encoder,guard)
            products=[dict(product_id=str(p.product_id),eligible_train_dates=int(table.loc[table.product_key==str(p.product_id),'target_date'].nunique()),
                           eligible_train_tasks=int((table.product_key==str(p.product_id)).sum())) for p in data.products]
            candidates.append(dict(design=label,train_end=cut,distinct_train_dates=int(table.target_date.nunique()),products=products,
                minimum_required_dates=config.walk_forward_minimum_train_days,quarantined=excluded,
                meets_minimum=all(p['eligible_train_dates']>=config.walk_forward_minimum_train_days for p in products)))
        revised=BenchmarkOrigin.model_validate(task.model_dump(mode='python')|dict(train_end=task.origin-timedelta(days=48),point_start=task.origin-timedelta(days=47)))
        point=post_support(data,revised,revised.point_start,revised.point_end,revised.train_end,old,config,guard)
        cqr=post_support(data,revised,revised.calibration_start,revised.calibration_end,revised.point_end,old,config,guard)
        targets=[o for o in data.observations if task.origin<o.sales_date<=task.origin+timedelta(days=7)]
        rows.append(dict(origin=task.origin,partition=task.partition,history_rows=len(at_origin(data,task.origin)),
            warmup_minimum_observations=config.minimum_history_observations,training=candidates,proposed_windows=revised,
            point=point,calibration=cqr,target_dates=(task.origin+timedelta(days=1),task.origin+timedelta(days=7)),
            masks=dict(Counter('primary_known_false' if o.is_stockout is False else 'censored' if o.is_stockout else 'unknown' for o in targets)),
            calendar='FULL_ACTUAL_ROWS_WITH_BENCHMARK_ASSUMED_AVAILABILITY',
            admissible=candidates[-1]['meets_minimum'] and point['minimum_horizon_tasks']>=spec['minimum_group_tasks'] and
                point['minimum_horizon_dates']>=spec['minimum_group_distinct_target_dates'] and cqr['minimum_horizon_tasks']>=config.minimum_calibration_samples))
        print(canonical_bytes(rows[-1]).decode(),flush=True)
    report=dict(status='SUPPORT_VERIFIED_NO_FITS' if all(r['admissible'] for r in rows) else 'BLOCKED_SUPPORT',
        design='train_origin_minus48_point20_calibration28_strict_all_holdout_quarantine',rows=rows,
        cache_entries=len(guard.native_cache.frames),cache_hits=guard.native_cache.hits,booster_fits=guard.boosters,
        old_origin_shift='Four weekly origins ending with observed 7-day targets must begin no later than June10; original cut support is insufficient there.',
        source_revision=data.source_revision,declaration_digest=challenger_digest('demo-calendar-assumption',declaration))
    digest=challenger_digest('native-support',report)
    store.retain(directory,'support-'+digest+'.json',report)
    return directory,report


def main():
    import platform
    platform.uname()
    from scripts.run_demo_benchmark import install_offline_guard
    install_offline_guard()
    import lightgbm as lgb
    def forbidden(*a,**k): raise RuntimeError('SUPPORT_PREFLIGHT_MUST_NOT_FIT')
    lgb.train=forbidden
    directory,report=inspect(ROOT)
    print(canonical_bytes(dict(status=report['status'],inputs=str(directory))).decode())


if __name__=='__main__':main()
