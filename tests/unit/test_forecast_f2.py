"""Hand-checkable F2 method/policy invariants; never train boosters or open a DB."""
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from fractions import Fraction as F
import json
from pathlib import Path
import pytest
from pydantic import ValidationError
from app.domain.forecasting.endpoint_calibration import (
    ClosureFact, EndpointSample, EndpointFit, closure_state, common_closure,
    empirical_quantile, fit_endpoints, correct_endpoints, POLICY_VERSION,
)
from app.application.contracts.forecast_f2 import F2Protocol

NOW=datetime(2026,6,10,17,tzinfo=timezone.utc)
DAY=date(2026,6,11)


def test_shared_closure_same_facts_all_arms_and_no_double_override():
    state=closure_state((ClosureFact('s',DAY,True,False,NOW,'declared'),),'s',DAY,NOW)
    for q in ((F(1),F(2),F(3)),(F(4),F(5),F(6)),(F(7),F(8),F(9))):
        assert common_closure(q,(F(0),F(10)),state)==((0,0,0),(0,0))
        with pytest.raises(ValueError,match='ALREADY_APPLIED'):
            common_closure(q,None,state,applied_policy=POLICY_VERSION)


def test_unknown_holiday_and_late_calendar_do_not_change_predictions():
    q=(F(1),F(2),F(3))
    for fact in (None,ClosureFact('s',DAY,None,True,NOW,'x'),
                 ClosureFact('s',DAY,True,False,NOW+timedelta(seconds=1),'x'),
                 ClosureFact('s',DAY,True,False,None,'x')):
        state=closure_state(() if fact is None else (fact,),'s',DAY,NOW)
        assert state=='UNKNOWN' and common_closure(q,None,state)==(q,None)
    holiday=ClosureFact('s',DAY,False,True,NOW,'x')
    assert closure_state((holiday,),'s',DAY,NOW)=='OPEN'
    assert common_closure(q,None,'OPEN')==(q,None)
    with pytest.raises(ValueError,match='DUPLICATE_OR_CONFLICT'):
        closure_state((holiday,replace(holiday,closed=True)),'s',DAY,NOW)
    with pytest.raises(ValueError,match='STORE_CONFLICT'):
        closure_state((replace(holiday,store='foreign'),),'s',DAY,NOW)


def test_nearest_rank_quantile_is_inverse_empirical_cdf_not_interpolation():
    values=tuple(map(F,(40,10,30,20)))
    assert empirical_quantile(values,F(1,4))==(10,1)
    assert empirical_quantile(values,F(3,4))==(30,3)
    assert empirical_quantile((F(2),)*4,F(1,4))==(2,1)


def samples():
    start=date(2026,5,1)
    return tuple(EndpointSample(p,'ly',start+timedelta(days=d),start+timedelta(days=d-1),NOW,
        F(10),F(9),F(11)) for d in range(7) for p in ('a','b','c','d','e'))


def fit(rows):
    return fit_endpoints(rows,products=('a','b','c','d','e'),unit='ly',start=date(2026,5,1),end=date(2026,5,7),
        point_end=date(2026,4,30),forecast_origin=date(2026,6,10),available_at=NOW,quarantined=frozenset())


def test_endpoint_fit_known_residuals_sparse_support_and_p50_exact():
    result=fit(samples())
    assert result.status=='FITTED' and result.lower_delta==1 and result.upper_delta==-1
    assert result.lower_rank==9 and result.upper_rank==27
    assert fit(samples()[:20]).status=='NOT_FITTED'
    q,counts=correct_endpoints((F(9),F(10),F(11)),result)
    assert q==(10,10,10) and q[1]==F(10) and not counts['raw_crossing']
    wild=replace(result,lower_delta=F(100),upper_delta=F(-100))
    q,counts=correct_endpoints((F(9),F(10),F(11)),wild)
    assert q==(10,10,10) and counts['lower_median_clamp'] and counts['upper_median_clamp']
    q,counts=correct_endpoints((F(9),F(10),F(11)),replace(result,lower_delta=F(-100)))
    assert q[0]==0 and q[1]==10 and counts['lower_nonnegative_clamp']


def test_causal_fit_rejects_future_labels_wrong_unit_duplicates_and_windows():
    rows=samples()
    for changed in (replace(rows[0],known_at=NOW+timedelta(seconds=1)),
                    replace(rows[0],feature_origin=rows[0].target),
                    replace(rows[0],unit='kg'),replace(rows[0],target=date(2026,7,1))):
        with pytest.raises(ValueError):fit((changed,)+rows[1:])
    with pytest.raises(ValueError,match='DUPLICATE'):fit(rows+(rows[0],))


def test_frozen_f2_protocol_rejects_version_counts_and_origin_drift():
    raw=json.loads((Path(__file__).parents[1]/'fixtures/forecast_engine/benchmark_manifest_f2_v1.json').read_bytes())
    assert F2Protocol.model_validate(raw).maximum_booster_fits==0
    for key,value in (('protocol_version','forecast_f2/2'),('maximum_booster_fits',1),
                      ('wall_seconds',300.0),('minimum_tasks',20),('origins',raw['origins'][::-1])):
        with pytest.raises(ValidationError):F2Protocol.model_validate(raw|{key:value})


def application_context():
    from types import SimpleNamespace as NS
    from decimal import Decimal
    from uuid import UUID
    from app.application.contracts.forecast_benchmark import BenchmarkOrigin
    from app.application.forecast_benchmark_admission import next_run
    spec=F2Protocol.model_validate_json((Path(__file__).parents[1]/'fixtures/forecast_engine/benchmark_manifest_f2_v1.json').read_bytes())
    products=tuple(NS(product_id=UUID(int=i),selling_unit='ly') for i in range(1,6))
    tasks=tuple(BenchmarkOrigin(origin=o,partition='validation' if i<2 else 'holdout',
        train_end=date.fromisoformat(o)-timedelta(days=48),point_start=date.fromisoformat(o)-timedelta(days=47),
        point_end=date.fromisoformat(o)-timedelta(days=28),calibration_start=date.fromisoformat(o)-timedelta(days=27),calibration_end=o)
        for i,o in enumerate(spec.origins))
    first=date(2026,5,1);days=[first+timedelta(days=i) for i in range(70)]
    calendar=tuple(NS(store_id=UUID(int=99),day=d,closed=d==date(2026,6,11),holiday=False,available_at=NOW-timedelta(days=100),source='fictional') for d in days)
    observations=tuple(NS(product_id=p.product_id,sales_date=d,quantity=Decimal(0 if d==date(2026,6,11) else 20),
        is_stockout=False,available_at=next_run(d,'Asia/Ho_Chi_Minh')) for d in days for p in products)
    data=NS(store_id=UUID(int=99),products=products,calendar=calendar,observations=observations,timezone='Asia/Ho_Chi_Minh')
    plan=NS(tasks=tasks)
    task=tasks[0];rows=[]
    for d in days:
        if not task.calibration_start<=d<=task.calibration_end:continue
        for h in range(1,8):
            cutoff=d-timedelta(days=h)
            if cutoff<task.point_end:continue
            for p in products:
                rows.append(dict(product_key=str(p.product_id),store_key=str(data.store_id),unit='ly',target_date=str(d),
                    cutoff_date=str(cutoff),horizon=h,actual_known_at=next_run(d,data.timezone).isoformat(),
                    target=20,p25=19,p50=20,p75=21,target_store_closed=0))
    return data,plan,task,rows,spec


def test_calibration_future_outcome_invariance_and_parameter_tamper():
    from types import SimpleNamespace
    from decimal import Decimal
    import copy
    from app.application.forecast_f2 import fit_origin,validate_parameters,retained_value,validate_closed_sales
    data,plan,task,rows,spec=application_context()
    validate_closed_sales(data)
    p,e=fit_origin(data,plan,task,rows,spec)
    future=copy.deepcopy(data)
    for o in future.observations:
        if o.sales_date>task.origin:o.quantity+=Decimal(100)
    assert fit_origin(future,plan,task,rows,spec)==(p,e)
    p,e=retained_value(p),retained_value(e)
    validate_parameters(p,e,data,plan,task,rows,spec)
    bad=copy.deepcopy(p);bad['groups']['1']['lower_delta']='999'
    with pytest.raises(ValueError,match='ARITHMETIC'):validate_parameters(bad,e,data,plan,task,rows,spec)
    bad=copy.deepcopy(p);bad['method']='other/1'
    with pytest.raises(ValueError,match='VERSION'):validate_parameters(bad,e,data,plan,task,rows,spec)
    bad=copy.deepcopy(rows);bad[0]['actual_known_at']=(NOW+timedelta(days=1)).isoformat()
    with pytest.raises(ValueError,match='AVAILABILITY'):fit_origin(data,plan,task,bad,spec)
    conflict=copy.deepcopy(data)
    next(o for o in conflict.observations if o.sales_date==date(2026,6,11)).quantity=Decimal(1)
    with pytest.raises(ValueError,match='POSITIVE_SALES'):validate_closed_sales(conflict)


def test_c1_preserves_p50_units_cqr_and_single_closure_from_prepolicy_arrays():
    from app.application.forecast_f2 import fit_origin,retained_value,forecasts
    data,plan,task,rows,spec=application_context()
    p,_=fit_origin(data,plan,task,rows,spec);product=str(data.products[0].product_id)
    predictions=[]
    for arm in ('A','B','C'):
        predictions.append(dict(arm=arm,store_id=str(data.store_id),product_id=product,selling_unit='ly',origin=str(task.origin),
            target_date='2026-06-11',horizon=1,partition='validation',mask='primary_known_false',actual='0',
            p25='0' if arm=='C' else '10',p50='0' if arm=='C' else '20',p75='0' if arm=='C' else '30',
            cqr_lower='0' if arm=='C' else None,cqr_upper='0' if arm=='C' else None,raw_crossing=False))
    evidence={str(task.origin):dict(output=dict(native_predictions=[dict(product_id=product,forecast_date='2026-06-11',
        repaired=['10','20','30'],point_offset='0',planned_closed=True)],cqr=[dict(product_id=product,forecast_date='2026-06-11',correction='2')]))}
    variants,audits=forecasts(data,predictions,evidence,{str(task.origin):retained_value(p)})
    for variant in ('A_common','B_common','C0','C1'):
        assert tuple(variants[variant][0][q] for q in ('p25','p50','p75'))==(0,0,0)
        assert variants[variant][0]['selling_unit']=='ly'
    assert variants['C1'][0]['cqr_upper']==variants['C0'][0]['cqr_upper']==0
    assert all(a['policy_applications']==1 for a in audits)
    assert audits[-1]['before_policy']==(10,20,30) and audits[-1]['C1_policy_applications']==1


@pytest.mark.parametrize('tamper',['source','dataset','artifact','version'])
def test_admission_detects_source_dataset_artifact_and_version_tamper(tmp_path,monkeypatch,tamper):
    import sys
    from types import SimpleNamespace as NS
    from app.infrastructure import forecast_f2_harness as harness
    from app.infrastructure.forecast_benchmark_storage import BenchmarkStorage
    from app.application.forecast_challenger_serialization import challenger_digest
    fixture=Path(__file__).parents[1]/'fixtures/forecast_engine/benchmark_manifest_f2_v1.json'
    spec=F2Protocol.model_validate_json(fixture.read_bytes())
    for n in ('dep.py','dataset.json','artifact.txt'):(tmp_path/n).write_text('original',encoding='utf-8')
    protocol=tmp_path/harness.PROTOCOL;protocol.parent.mkdir(parents=True);protocol.write_bytes(fixture.read_bytes())
    names=('dep.py',harness.PROTOCOL);monkeypatch.setattr(harness,'SOURCE_FILES',names)
    monkeypatch.setattr(harness,'current_runtime',lambda:NS(model_dump=lambda **k:{}))
    pins={n:harness.sha(tmp_path/n) for n in ('dataset.json','artifact.txt')}
    manifest=dict(protocol=spec,inputs=pins,source={n:harness.sha(tmp_path/n) for n in names},runtime={},python=sys.version,bindings={})
    identity=challenger_digest('f2-admission',manifest)
    store=BenchmarkStorage(tmp_path/'runtime/challenger/f2');out=store.path('experiments',identity)
    store.retain(out,'admission.json',manifest)
    monkeypatch.setattr(harness,'context',lambda root:(None,None,None,None,None,{},pins))
    harness.admitted(tmp_path,identity)
    name={'source':'dep.py','dataset':'dataset.json','artifact':'artifact.txt','version':harness.PROTOCOL}[tamper]
    if tamper=='version':
        raw=json.loads(protocol.read_bytes());raw['protocol_version']='forecast_f2/2';protocol.write_text(json.dumps(raw),encoding='utf-8')
    else:(tmp_path/name).write_text('tampered',encoding='utf-8')
    with pytest.raises((ValueError,ValidationError)):harness.admitted(tmp_path,identity)


def test_harness_replay_verifies_arithmetic_without_calling_fit(tmp_path,monkeypatch):
    from types import SimpleNamespace as NS
    from app.application.forecast_f2 import fit_origin,retained_value
    from app.infrastructure import forecast_f2_harness as harness
    from app.infrastructure.forecast_benchmark_storage import BenchmarkStorage
    data,plan,task,table,spec=application_context();parameters,evidence=fit_origin(data,plan,task,table,spec)
    identity='a'*64;origin=str(task.origin);binding={'parent_artifact':'b'*64}
    parameters.update(binding);parameters['f2_identity']=identity
    store=BenchmarkStorage(tmp_path);out=store.path('experiments',identity)
    store.retain(out,origin+'-parameters.json',retained_value(parameters));store.retain(out,origin+'-fit-evidence.json',retained_value(evidence))
    ctx=(data,NS(tasks=(task,)),[],{origin:table},{},{origin:binding},{})
    monkeypatch.setattr(harness,'admitted',lambda *a:(store,out,spec,ctx))
    def forbidden(*a,**k):pytest.fail('Replay may not fit')
    monkeypatch.setattr(harness,'fit_origin',forbidden)
    monkeypatch.setattr('app.application.forecast_f2.fit_endpoints',forbidden)
    monkeypatch.setattr(harness,'result_values',lambda *a:{'summary.json':{'verified':'saved-array'}})
    store.retain(out,'summary.json',{'verified':'saved-array'})
    report=harness.replay(tmp_path,identity,attempts=[])
    assert report['endpoint_fits']==0 and report['status']=='F2_READONLY_REPLAY_VERIFIED'
    parameters['groups']['1']['lower_delta']=F(100)
    # A forged, internally rehashed envelope still fails arithmetic validation.
    (out/(origin+'-parameters.json')).unlink()
    store.retain(out,origin+'-parameters.json',retained_value(parameters))
    with pytest.raises(ValueError,match='ARITHMETIC'):harness.replay(tmp_path,identity,attempts=[])


def test_consumed_child_batch_claim_rejects_before_any_endpoint_fit(tmp_path,monkeypatch):
    from app.infrastructure import forecast_f2_harness as harness
    from app.infrastructure.forecast_benchmark_storage import BenchmarkStorage
    identity='a'*64;store=BenchmarkStorage(tmp_path);out=store.path('experiments',identity)
    out.mkdir(parents=True);(out/'execution-claim.json').write_text('previous consumed attempt',encoding='utf-8')
    store.retain(store.root,'bounded-batch-start.json',{'identity':identity})
    monkeypatch.setattr(harness,'admitted',lambda *a:(store,out,None,(None,)*7))
    def forbidden(*a,**k):pytest.fail('Consumed batch must not fit')
    monkeypatch.setattr(harness,'fit_origin',forbidden)
    with pytest.raises(FileExistsError):harness.execute(tmp_path,identity,attempts=[])


def test_quarantined_label_rejects_even_within_chronological_calibration_window():
    sample=EndpointSample('a','ly',date(2026,6,25),date(2026,6,24),NOW,F(10),F(9),F(11))
    with pytest.raises(ValueError,match='LABEL_NOT_ELIGIBLE'):
        fit_endpoints((sample,),products=('a',),unit='ly',start=date(2026,6,4),end=date(2026,7,1),
            point_end=date(2026,6,3),forecast_origin=date(2026,7,1),available_at=NOW,
            quarantined=frozenset({sample.target}))


def test_validation_rule_rejects_cross_group_regression_and_ignores_evaluation():
    from app.application.forecast_f2 import validation_decision
    base=dict(partition='validation',mask='primary_known_false',cohort='OPEN',dimension='all',value='all',
        pinball=(F(2),F(1),F(2)),below_p25=F(2,5),above_p75=F(2,5))
    rows=[base|dict(variant='C0'),base|dict(variant='C1',pinball=(F(1),F(1),F(1)),below_p25=F(1,4),above_p75=F(1,4))]
    parameters={'2026-06-10':{'status':'FITTED'},'2026-06-17':{'status':'FITTED'}}
    assert validation_decision(rows,parameters)['selected_endpoint_variant']=='C1'
    rows += [base|dict(variant='C0',dimension='product_horizon',value='p/7'),
             base|dict(variant='C1',dimension='product_horizon',value='p/7',pinball=(F(3),F(1),F(3)))]
    rows.append(base|dict(variant='C1',partition='holdout',pinball=(F(0),)*3))
    result=validation_decision(rows,parameters)
    assert result['selected_endpoint_variant']=='C0' and len(result['validation_regressions'])==1
