"""E3 causal protocol/metrics correctness. Native fits are verified separately by smoke/run."""
from datetime import timedelta
from decimal import Decimal

import pytest

from app.application.contracts.forecast_benchmark import BenchmarkDataset, BenchmarkPlan, BenchmarkBudget
from app.application.forecast_benchmark_admission import admit_plan, at_origin, calendar_at_origin, holdout_dates
from app.application.forecast_challenger_serialization import challenger_digest
from app.application.contracts.forecast_challenger import ChallengerError
from app.domain.forecasting.benchmark_metrics import Score, metrics
from app.infrastructure.forecast_benchmark_storage import FitBudget, BudgetExceeded
from app.infrastructure.forecast_benchmark_features import native_frame, prepared_at
from tests.fixtures.forecast_engine.benchmark_setup import synthetic_benchmark


def test_frozen_corpus_split_windows_and_heldout_quarantine():
    data,plan=synthetic_benchmark()
    admit_plan(data,plan)
    assert len(plan.tasks)==4 and len(holdout_dates(plan))==14
    assert plan.dataset_digest==challenger_digest('dataset',data)
    changed=plan.model_dump(mode='python')
    changed['tasks'][0]['point_end']+=timedelta(days=1)
    with pytest.raises(ChallengerError,match='FROZEN_WINDOWS'):
        admit_plan(data,BenchmarkPlan.model_validate(changed))


def test_metrics_hand_calculation_zero_denominator_and_mixed_units():
    data,plan=synthetic_benchmark()
    day=plan.tasks[0].origin
    rows=(Score('s','p',day,'cup',Decimal(10),(Decimal(0),Decimal(8),Decimal(16)),(Decimal(6),Decimal(18))),
          Score('s','q',day,'piece',Decimal(0),(Decimal(0),Decimal(0),Decimal(0)),(Decimal(0),Decimal(0))))
    result=metrics(rows)
    assert result['mae']==1 and result['wape']==Decimal('.2') and result['bias']==-1
    assert result['pinball']==(Decimal('1.25'),Decimal('.5'),Decimal('.75'))
    assert abs(result['mean_pinball']-Decimal(5)/6)<Decimal('1e-27')
    assert result['mixed_units'] and result['cqr_coverage']==1
    zero=metrics(rows[1:])
    assert zero['wape'] is None and zero['normalized_bias'] is None
    assert metrics(())['mean_pinball'] is None
    overlapping=metrics(rows+(rows[0],))
    assert overlapping['task_count']==3 and overlapping['distinct_outcomes']==2 and overlapping['distinct_dates']==1


def test_future_observations_do_not_change_earlier_native_or_host_features():
    from shelfcash_forecast.config import ForecastConfig
    data,plan=synthetic_benchmark()
    origin=plan.tasks[0].train_end
    config=ForecastConfig()
    before_panel,before=native_frame(data,origin,config)
    values=data.model_dump(mode='python')
    for row in values['observations']:
        if row['sales_date']>origin:
            row['quantity']=Decimal('99999')
    changed=BenchmarkDataset.model_validate(values)
    after_panel,after=native_frame(changed,origin,config)
    assert before.equals(after) and before_panel.equals(after_panel)
    assert prepared_at(data,origin)==prepared_at(changed,origin)


def test_calendar_missing_is_blocked_not_default_open_and_late_labels_are_absent():
    data,plan=synthetic_benchmark()
    origin=plan.tasks[0].origin
    values=data.model_dump(mode='python')
    values['calendar']=()
    with pytest.raises(ChallengerError,match='SOURCED_CALENDAR_NOT_AVAILABLE'):
        calendar_at_origin(BenchmarkDataset.model_validate(values),origin)
    values=data.model_dump(mode='python')
    row=next(o for o in values['observations'] if o['sales_date']==origin)
    row['available_at']+=timedelta(days=2)
    changed=BenchmarkDataset.model_validate(values)
    assert len(at_origin(changed,origin))==len(at_origin(data,origin))-1


def test_missing_zero_and_unknown_remain_explicit():
    data,plan=synthetic_benchmark()
    assert any(o.quantity==0 for o in data.observations)
    assert any(o.is_stockout is None for o in data.observations)
    assert len(data.observations)<2*(max(o.sales_date for o in data.observations)-min(o.sales_date for o in data.observations)).days


def test_fit_budget_is_bounded_and_does_not_extend():
    guard=FitBudget(BenchmarkBudget(maximum_booster_fits=1,maximum_postprocess_fits=1))
    guard.booster()
    with pytest.raises(BudgetExceeded,match='BOOSTER_FIT_BUDGET_EXCEEDED'):
        guard.booster()
    guard.calibration()
    with pytest.raises(BudgetExceeded,match='POSTPROCESS_FIT_BUDGET_EXCEEDED'):
        guard.calibration()


def test_paired_masks_and_validation_only_selection_ignore_holdout_scores():
    from app.application.contracts.forecast_benchmark import ARMS, ArmCheckpoint, BenchmarkPrediction
    from app.application.forecast_benchmark_reporting import summary, attach_targets
    data,plan=synthetic_benchmark()
    checkpoints=[]
    for task in plan.tasks:
        for arm in ARMS:
            predictions=[]
            for product in data.products:
                for h in range(1,8):
                    day=task.origin+timedelta(days=h)
                    actual=next((o.quantity for o in data.observations if o.product_id==product.product_id and o.sales_date==day),Decimal(0))
                    # C wins validation; A wins holdout. Only validation chooses the family.
                    error=0 if (arm==ARMS[2])==(task.partition=='validation') else 100
                    value=actual+error
                    predictions.append(BenchmarkPrediction(arm=arm,store_id=data.store_id,product_id=product.product_id,
                        selling_unit=product.selling_unit,origin=task.origin,partition=task.partition,target_date=day,
                        horizon=h,actual=None,stockout=None,mask='missing',p25=value,p50=value,p75=value))
            checkpoints.append(ArmCheckpoint(arm=arm,origin=task.origin,identity='a'*64,status='COMPLETED',reason=None,
                predictions=tuple(predictions),input_digest='a'*64,training_seconds=Decimal(0),inference_seconds=Decimal(0)))
    report=summary(data,plan,tuple(checkpoints),complete=True)
    assert report['selected_by_validation_only']==ARMS[2]
    assert report['masks']=={'primary_known_false':50,'censored_lower_bound':2,'missing':2,'supplementary_unknown':2}
    assert report['paired_tasks']==56 and not report['accuracy_numeric_gate']
    assert report['production']=='LOCKED' and report['promotion_evidence']=='INSUFFICIENT_EVIDENCE'
    for offset in range(0,12,3):
        masks=[tuple((p.product_id,p.target_date,p.actual,p.mask) for p in attach_targets(data,c)) for c in checkpoints[offset:offset+3]]
        assert masks[0]==masks[1]==masks[2]


def test_fit_identity_ignores_future_targets_but_binds_eligible_history():
    from pathlib import Path
    from app.application.contracts.forecast_benchmark import ARMS
    from app.application.use_cases.forecast_benchmark import load_protocol
    from app.infrastructure.forecast_benchmark_training import fit_identity
    data,plan=synthetic_benchmark()
    task=plan.tasks[0]
    protocol=load_protocol(Path(__file__).resolve().parents[2])
    config=protocol['arm_configuration'][ARMS[2]]
    identity=fit_identity(data,plan,task,ARMS[2],config)
    values=data.model_dump(mode='python')
    for row in values['observations']:
        if row['sales_date']>task.origin:
            row['quantity']=Decimal(99999)
    changed=BenchmarkDataset.model_validate(values)
    assert fit_identity(changed,plan,task,ARMS[2],config)==identity
    values['observations'][0]['quantity']+=1
    assert fit_identity(BenchmarkDataset.model_validate(values),plan,task,ARMS[2],config)!=identity


def test_checkpoint_envelope_rejects_changed_payload(tmp_path):
    import json
    from app.infrastructure.forecast_benchmark_storage import BenchmarkStorage
    storage=BenchmarkStorage(tmp_path)
    directory=storage.path('fits','a'*64)
    storage.retain(directory,'checkpoint.json',{'quantity':1})
    storage.retain(directory,'checkpoint.json',{'quantity':1})
    path=directory/'checkpoint.json'
    envelope=json.loads(path.read_bytes())
    envelope['value']['quantity']=2
    path.write_text(json.dumps(envelope))
    with pytest.raises(ChallengerError,match='BENCHMARK_DIGEST_MISMATCH'):
        storage.load(directory,'checkpoint.json')


def test_resume_cannot_reset_spent_wall_budget(tmp_path,monkeypatch):
    from pathlib import Path
    from app.application.use_cases.forecast_benchmark import ForecastBenchmark
    from app.infrastructure.forecast_benchmark_storage import BenchmarkStorage
    service=ForecastBenchmark(Path(__file__).resolve().parents[2])
    service.storage=BenchmarkStorage(tmp_path)
    data,plan=synthetic_benchmark()
    _,directory,_=service.freeze(data,plan)
    service.storage.retain(directory,'resource-ledger-'+('a'*64)+'.json',
        {'spent_seconds':300,'boosters':3,'postprocess':1})
    def forbidden_fit(*args,**kwargs):
        pytest.fail('Spent budget must stop before fitting')
    monkeypatch.setattr('app.application.use_cases.forecast_benchmark.fit_arm',forbidden_fit)
    report=service.run(data,plan)
    assert report['status']=='INCOMPLETE'
    assert report['exclusions'][0]['status']=='BUDGET_EXCEEDED'
    assert report['booster_fits_spent']==3 and report['postprocess_fits_spent']==1
