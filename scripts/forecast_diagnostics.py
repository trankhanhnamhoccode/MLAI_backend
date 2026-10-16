"""Independent F1 audit of retained arrays only. No inference, fitting or operational IO."""
import argparse
from dataclasses import replace
from datetime import date,timedelta
from decimal import Decimal,localcontext
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def serial(value):
    if isinstance(value,F):
        with localcontext() as ctx:
            ctx.prec=40
            return str(Decimal(value.numerator)/Decimal(value.denominator))
    if isinstance(value,dict):return {str(k):serial(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)):return [serial(v) for v in value]
    return value


def close(a,b,tolerance=F(1,10**25)):
    if a is None or b is None:return a is None and b is None
    if isinstance(a,bool) or isinstance(b,bool):return a is b
    if isinstance(a,(tuple,list)):return len(a)==len(b) and all(close(x,y,tolerance) for x,y in zip(a,b))
    return abs(F(a)-F(str(b)))<=tolerance


def audit(experiment:str):
    from app.domain.forecasting.diagnostics import Point,score,sensitivity
    from app.infrastructure.forecast_benchmark_storage import BenchmarkStorage
    from app.infrastructure.storage.forecast_challenger import ChallengerStorage
    from app.application.forecast_challenger_serialization import challenger_digest
    store=BenchmarkStorage(ROOT/'runtime/challenger/benchmarks');directory=store.path('experiments',experiment)
    inputs={}
    def load(folder,name):
        path=folder/name;inputs[str(path.relative_to(ROOT))]=hashlib.sha256(path.read_bytes()).hexdigest()
        return store.load(folder,name)
    rows=load(directory,'predictions.json');official=load(directory,'summary.json');data=load(directory,'dataset.json');plan=load(directory,'plan.json')
    observations={(o['product_id'],o['sales_date']):o for o in data['observations']}
    calendar={r['day']:r for r in data['calendar']};units={p['product_id']:p['selling_unit'] for p in data['products']}
    points={};groups={a:[] for a in ('A','B','C')}
    for r in rows:
        if (date.fromisoformat(r['target_date'])-date.fromisoformat(r['origin'])).days!=r['horizon']:raise ValueError('TARGET_ALIGNMENT')
        actual=observations.get((r['product_id'],r['target_date']))
        mask='missing' if actual is None else 'censored_lower_bound' if actual['is_stockout'] is True else 'primary_known_false' if actual['is_stockout'] is False else 'supplementary_unknown'
        if r['mask']!=mask or r['actual']!=(None if actual is None else actual['quantity']) or r['selling_unit']!=units[r['product_id']]:
            raise ValueError('ACTUAL_MASK_OR_UNIT_MISMATCH')
        if actual is None:continue
        p=Point(r['product_id'],r['selling_unit'],r['origin'],r['target_date'],r['partition'],r['horizon'],F(r['actual']),
            tuple(F(r[q]) for q in ('p25','p50','p75')),None if r['cqr_lower'] is None else (F(r['cqr_lower']),F(r['cqr_upper'])),r['raw_crossing'])
        points[r['arm'][0],p.product,p.origin,p.horizon]=p
        if mask=='primary_known_false':groups[r['arm'][0]].append(p)
    groups={a:tuple(p) for a,p in groups.items()}
    recomputed=[]
    for expected in official['metrics']:
        matched=[]
        for r in rows:
            if (r['arm'],r['partition'],r['mask'])!=(expected['arm'],expected['partition'],expected['mask']):continue
            dim,value=expected['dimension'],expected['value']
            if dim=='product' and r['product_id']!=value:continue
            if dim=='horizon' and r['horizon']!=value:continue
            if dim=='product_horizon' and f"{r['product_id']}/{r['horizon']}"!=value:continue
            if dim=='unit' and r['selling_unit']!=value:continue
            if r['actual'] is not None:matched.append(points[r['arm'][0],r['product_id'],r['origin'],r['horizon']])
        independent=score(tuple(matched))
        for key in ('task_count','distinct_outcomes','distinct_dates','mae','wape','bias','normalized_bias','pinball','mean_pinball',
                    'quantile_coverage','quantile_width','cqr_coverage','cqr_width','raw_crossings','mixed_units'):
            if not close(independent[key],expected[key]):raise ValueError('INDEPENDENT_METRIC_MISMATCH:'+key)
        recomputed.append({k:expected[k] for k in ('arm','partition','mask','dimension','value')}|independent)
    stages=[];stage_groups={};detail=[];horizon_rows=[];calibration_audits=[];host_features=[]
    artifacts=ChallengerStorage(ROOT/'runtime/challenger')
    c_no_closure=[];equal_closure={a:tuple(replace(p,quantiles=(F(0),)*3) if calendar[p.target]['closed'] else p for p in g) for a,g in groups.items()}
    for task in plan['tasks']:
        origin=task['origin'];checkpoint=load(directory,origin+'-C_engine_native_reconstruction_v1.json')
        bundle=artifacts.load_artifact(checkpoint['artifact_identity']);evidence=artifacts.load_evidence(checkpoint['replay_identity'])
        for name in ('adapter_manifest.json',*[f.name for f in bundle.manifest.files]):
            inputs[str((bundle.directory/name).relative_to(ROOT))]=hashlib.sha256((bundle.directory/name).read_bytes()).hexdigest()
        evidence_path=ROOT/'runtime/challenger/runs'/checkpoint['replay_identity']/'evidence.json'
        inputs[str(evidence_path.relative_to(ROOT))]=hashlib.sha256(evidence_path.read_bytes()).hexdigest()
        native={str(r.product_id)+'/'+str(r.forecast_date):r for r in evidence.output.native_predictions}
        intervals={str(r.product_id)+'/'+str(r.forecast_date):r for r in evidence.output.cqr}
        for p in (p for p in groups['C'] if p.origin==origin):
            n=native[p.product+'/'+p.target];interval=intervals[p.product+'/'+p.target]
            raw=tuple(F(v) for v in n.quantity_raw);repaired=tuple(F(v) for v in n.repaired)
            expected_raw=tuple(max(0.,float(n.seasonal_anchor)+float(v)) for v in n.model_raw)
            if not all(close(v,str(e),F(1,10**10)) for v,e in zip(raw,expected_raw)):raise ValueError('RESIDUAL_ANCHOR_MISMATCH')
            if repaired!=tuple(sorted(raw)):raise ValueError('REARRANGEMENT_MISMATCH')
            corrected=tuple(F(str(max(0.,float(v)+float(n.point_offset)))) for v in n.repaired)
            final=(F(0),)*3 if n.planned_closed else corrected
            if not all(close(v,e,F(1,10**10)) for v,e in zip(p.quantiles,final)):raise ValueError('POINT_OR_CLOSURE_MISMATCH')
            lower=min(max(F(0),corrected[0]-F(interval.correction)),corrected[1]);upper=max(corrected[2]+F(interval.correction),corrected[1])
            expected_interval=(F(0),F(0)) if n.planned_closed else (lower,upper)
            if not all(close(v,e,F(1,10**10)) for v,e in zip(p.interval,expected_interval)):raise ValueError('CQR_OUTPUT_MISMATCH')
            if n.anchor_reference_date and n.anchor_reference_date>date.fromisoformat(origin):raise ValueError('FUTURE_ANCHOR')
            for stage,q in (('quantity_raw_clipped',raw),('rearranged_before_point',repaired),('point_before_closure',corrected),('official_final',p.quantiles)):
                stage_groups.setdefault((p.partition,stage),[]).append(replace(p,quantiles=q,interval=None))
            c_no_closure.append(replace(p,quantiles=corrected,interval=None))
            detail.append(dict(product=p.product,origin=origin,target=p.target,horizon=p.horizon,partition=p.partition,
                quantity_raw=raw,repaired=repaired,point_offset=F(n.point_offset),point_before_closure=corrected,final=p.quantiles,
                median_changed_by_sort=raw[1]!=repaired[1],width_changed_by_point=not close(corrected[2]-corrected[0],repaired[2]-repaired[0],F(1,10**10)),
                clipped_quantity_count=sum(float(n.seasonal_anchor)+float(v)<0 for v in n.model_raw),
                clipped_point_count=sum(float(v)+float(n.point_offset)<0 for v in n.repaired),closed=n.planned_closed,
                anchor=F(n.seasonal_anchor),anchor_fallback=n.anchor_fallback,anchor_warning=n.anchor_warning))
            if p.horizon==6:
                horizon_rows.append(dict(origin=origin,target=p.target,weekday=date.fromisoformat(p.target).strftime('%A'),product=p.product,
                    actual=p.actual,closed=calendar[p.target]['closed'],holiday=calendar[p.target]['holiday'],
                    A=points['A',p.product,origin,6].quantiles[1],B=points['B',p.product,origin,6].quantiles[1],C=p.quantiles[1],
                    anchor=F(n.seasonal_anchor),raw_p50=raw[1],repaired_p50=repaired[1],point_offset=F(n.point_offset),
                    pre_closure_p50=corrected[1],anchor_fallback=n.anchor_fallback,anchor_warning=n.anchor_warning))
        fit=store.path('fits',checkpoint['identity'])
        forbidden={date.fromisoformat(t['origin'])+timedelta(days=h) for t in plan['tasks'] if t['partition']=='holdout' for h in range(1,8)}
        for name,start,end,available in (('training-table.json',None,task['train_end'],None),
            ('point-tasks.json',task['point_start'],task['point_end'],task['train_end']),
            ('calibration-tasks.json',task['calibration_start'],task['calibration_end'],task['point_end'])):
            table=load(fit,name)
            for r in table:
                cutoff=date.fromisoformat(r['cutoff_date'][:10]);target=date.fromisoformat(r['target_date'][:10])
                if not cutoff<target<=date.fromisoformat(end) or target in forbidden:raise ValueError('FIT_TEMPORAL_LEAKAGE')
                if start and (target<date.fromisoformat(start) or cutoff<date.fromisoformat(available)):raise ValueError('POSTPROCESS_AVAILABILITY')
            if name=='calibration-tasks.json':
                calibrator=json.loads((bundle.directory/'calibrator.json').read_bytes())
                errors=[]
                for h,v in calibrator['by_horizon'].items():
                    selected=[r for r in table if r['horizon']==int(h)]
                    scores=sorted(max(float(r['p25'])-float(r['target']),float(r['target'])-float(r['p75'])) for r in selected)
                    from math import ceil
                    correction=scores[ceil((len(scores)+1)*calibrator['desired_coverage'])-1]
                    errors.append(abs(correction-v['correction']))
                if max(errors)>1e-8:raise ValueError('CQR_RETAINED_PARAMETER_ARITHMETIC')
                calibration_audits.append(dict(origin=origin,rows=len(table),maximum_correction_rounding_delta=max(errors),
                    note='Saved DataFrame arrays have10-digit decimal serialization; parameter comparison tolerance1e-8, not bitwise fit reproduction.'))
        host=load(directory,origin+'-B_be_lightgbm_causal_v1.json');host_fit=store.path('fits',host['identity'])
        model=load(host_fit,'host-model.json')
        from app.application.forecast_serialization import restore_prepared
        from app.application.forecast_demand import usable_histories
        from app.domain.forecasting.features import FEATURE_NAMES,feature_values
        prepared=restore_prepared(model['prepared'],1,model['input_digest'])
        for code,(product,history) in enumerate(usable_histories(prepared).items()):
            features=dict(zip(FEATURE_NAMES,feature_values(history,prepared.request.cutoff_date,6,code)))
            host_features.append(dict(origin=origin,product=str(product),horizon=6,features=features,missing=[k for k,v in features.items() if v is None]))
    stages=[dict(partition=partition,stage=stage,**score(tuple(ps))) for (partition,stage),ps in stage_groups.items()]
    sensitivity_report=sensitivity(groups)
    sensitivity_report['equal_calendar_zero_override_ARRAY_COUNTERFACTUAL_ONLY']={a:score(tuple(p for p in rows if p.partition=='holdout')) for a,rows in equal_closure.items()}
    sensitivity_report['C_without_closure_override_ARRAY_COUNTERFACTUAL_ONLY']=score(tuple(p for p in c_no_closure if p.partition=='holdout'))
    summary=dict(status='INDEPENDENT_METRICS_AND_STAGE_AUDIT_VERIFIED',experiment=experiment,metric_groups_checked=len(recomputed),
        tie_policy='coverage inclusive; y<P25 strict; y<=P50 inclusive; y>P75 strict; ties counted separately',
        stage_rounding_tolerance='1e-10 for saved full-precision inference;1e-8 for10-digit fit tables',
        source_semantics='residual+anchor then nonnegative clip; sort; common point shift all3 then clip; separate CQR; factual closure zeros last',
        counts=dict(primary_C=len(groups['C']),raw_crossings_primary=sum(p.raw_crossing for p in groups['C']),
            raw_crossing_tasks=official['raw_crossing_tasks'],median_changed_by_sort=sum(r['median_changed_by_sort'] for r in detail),
            quantity_clamps=sum(r['clipped_quantity_count'] for r in detail),point_clamps=sum(r['clipped_point_count'] for r in detail),
            closed_primary=sum(r['closed'] for r in detail)),
        aggregate=[dict(arm=a,partition=part,**score(tuple(p for p in g if p.partition==part))) for a,g in groups.items() for part in ('validation','holdout')],
        sensitivity=sensitivity_report,calibration_parameter_checks=calibration_audits,training_calls=0,
        limitations=('No candidate fitted; counterfactuals are saved-array diagnostics only.','/3 holdout is exposed development evidence for F2.',
            'Saved fit-frame precision limits exact arithmetic reconstruction; no ablation of model learning was performed.'))
    source_files=('scripts/forecast_diagnostics.py','app/domain/forecasting/diagnostics.py')
    source={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in source_files}
    identity=challenger_digest('f1-diagnostics',dict(inputs=inputs,source=source))
    output=BenchmarkStorage(ROOT/'runtime/challenger/f1').path('diagnostics',identity)
    destination=BenchmarkStorage(ROOT/'runtime/challenger/f1')
    for name,value in (('summary.json',summary),('metrics.json',recomputed),('stages.json',dict(aggregate=stages,rows=detail)),
                       ('horizon6.json',dict(predictions=horizon_rows,host_features=host_features)),('provenance.json',dict(inputs=inputs,source=source))):
        destination.retain(output,name,serial(value))
    return dict(status=summary['status'],diagnostics=str(output),groups_checked=len(recomputed),training_calls=0)


def main():
    import platform
    platform.uname()
    from scripts.run_demo_benchmark import install_offline_guard
    install_offline_guard()
    import lightgbm as lgb
    def forbidden(*a,**k):raise RuntimeError('DIAGNOSTICS_CANNOT_TRAIN')
    lgb.train=forbidden
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--experiment',required=True)
    args=parser.parse_args()
    print(json.dumps(audit(args.experiment)))


if __name__=='__main__':main()
