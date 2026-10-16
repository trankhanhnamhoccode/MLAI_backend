"""Explicit F2 retained-array computation; no filesystem, training, HTTP or DB."""
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal, localcontext
from fractions import Fraction as F

from app.application.forecast_benchmark_admission import next_run, holdout_dates
from app.domain.forecasting.diagnostics import Point, score
from app.domain.forecasting.endpoint_calibration import (
    ClosureFact, EndpointSample, EndpointFit, closure_state, common_closure,
    fit_endpoints, correct_endpoints, empirical_quantile, POLICY_VERSION,
)


def retained_value(value):
    if isinstance(value,F):
        with localcontext() as context:
            context.prec=40
            return str(Decimal(value.numerator)/Decimal(value.denominator))
    if isinstance(value,(date,datetime)):return value.isoformat()
    if isinstance(value,dict):return {str(k):retained_value(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)):return [retained_value(v) for v in value]
    return value


def facts_for(data):
    return tuple(ClosureFact(str(c.store_id), c.day, c.closed, c.holiday, c.available_at, c.source)
                 for c in data.calendar)


def validate_closed_sales(data):
    calendar={c.day:c for c in data.calendar}
    if len(calendar)!=len(data.calendar) or any(c.store_id!=data.store_id for c in data.calendar):
        raise ValueError('F2_CALENDAR_SCOPE_OR_DUPLICATE')
    for o in data.observations:
        if o.sales_date in calendar and calendar[o.sales_date].closed and o.quantity>0:
            raise ValueError('F2_POSITIVE_SALES_ON_DECLARED_CLOSURE')


def endpoint_samples(data,plan,task,table):
    facts=facts_for(data);store=str(data.store_id)
    actuals={(str(o.product_id),o.sales_date):o for o in data.observations}
    units={str(p.product_id):p.selling_unit for p in data.products}
    forbidden=holdout_dates(plan)
    samples={h:[] for h in range(1,8)};excluded=Counter()
    keys=set()
    for r in table:
        product=r['product_key'];target=date.fromisoformat(r['target_date'][:10])
        origin=date.fromisoformat(r['cutoff_date'][:10]);h=r['horizon']
        key=product,origin,target
        if key in keys:raise ValueError('F2_DUPLICATE_CALIBRATION_TASK')
        keys.add(key)
        if (r['store_key']!=store or product not in units or r['unit']!=units[product]
                or type(h) is not int or not 1<=h<=7 or (target-origin).days!=h):
            raise ValueError('F2_CALIBRATION_SCOPE_UNIT_ALIGNMENT')
        if not task.point_end<=origin<target or not task.calibration_start<=target<=task.calibration_end or target in forbidden:
            raise ValueError('F2_CALIBRATION_WINDOW_OR_QUARANTINE')
        actual=actuals.get((product,target))
        if (actual is None or actual.is_stockout is not False or Decimal(str(r['target']))!=actual.quantity
                or datetime.fromisoformat(r['actual_known_at'])!=actual.available_at
                or actual.available_at>next_run(task.calibration_end,data.timezone)):
            raise ValueError('F2_CALIBRATION_LABEL_AVAILABILITY')
        if not Decimal(str(r['p25']))<=Decimal(str(r['p50']))<=Decimal(str(r['p75'])):
            raise ValueError('F2_CALIBRATION_QUANTILE_ORDER')
        state=closure_state(facts,store,target,next_run(origin,data.timezone))
        if state!='UNKNOWN' and bool(r['target_store_closed'])!=(state=='CLOSED'):
            raise ValueError('F2_CALIBRATION_CALENDAR_CONFLICT')
        if state!='OPEN':
            excluded[state]+=1
            continue
        samples[h].append(EndpointSample(product,r['unit'],target,origin,actual.available_at,
            F(actual.quantity),F(str(r['p25'])),F(str(r['p75']))))
    return {h:tuple(v) for h,v in samples.items()},dict(excluded)


def fit_origin(data,plan,task,table,spec):
    samples,excluded=endpoint_samples(data,plan,task,table)
    units={p.selling_unit for p in data.products}
    if len(units)!=1:raise ValueError('F2_SINGLE_UNIT_POOL_REQUIRED')
    groups={h:fit_endpoints(rows,products=tuple(str(p.product_id) for p in data.products),
        unit=next(iter(units)),start=task.calibration_start,end=task.calibration_end,
        point_end=task.point_end,forecast_origin=task.origin,available_at=next_run(task.origin,data.timezone),
        quarantined=holdout_dates(plan),minimum_tasks=spec.minimum_tasks,minimum_dates=spec.minimum_dates)
        for h,rows in samples.items()}
    fitted=all(f.status=='FITTED' for f in groups.values())
    parameters=dict(method=spec.endpoint_method,origin=str(task.origin),status='FITTED' if fitted else 'NOT_FITTED',
        reason=None if fitted else 'ONE_OR_MORE_HORIZONS_BELOW_FROZEN_MINIMUM',
        unit=next(iter(units)),groups={str(h):asdict(f) for h,f in groups.items()},
        cqr_dependency='Retained calibration predictions also fitted CQR; this method does not use its corrections. No split-conformal guarantee.',
        saved_prediction_precision='10 decimal digits; fit uses these retained arrays exactly',excluded=excluded)
    evidence={str(h):[asdict(s) for s in rows] for h,rows in samples.items()}
    return parameters,evidence


def restore_fit(raw):
    fields=dict(raw)
    fields['lower_delta']=F(raw['lower_delta']);fields['upper_delta']=F(raw['upper_delta'])
    fields['products']=tuple(raw['products'])
    return EndpointFit(**fields)


def validate_parameters(parameters,evidence,data,plan,task,table,spec):
    """Replay arithmetic proof from pinned samples; never call a fitting entrypoint."""
    samples,excluded=endpoint_samples(data,plan,task,table)
    if parameters['method']!=spec.endpoint_method or parameters['origin']!=str(task.origin) or parameters['excluded']!=excluded:
        raise ValueError('F2_PARAMETER_VERSION_OR_SCOPE')
    # Canonical scalar representation is shared with retained F1 diagnostics.
    if evidence!=retained_value({str(h):[asdict(s) for s in rows] for h,rows in samples.items()}):
        raise ValueError('F2_ENDPOINT_FIT_EVIDENCE_CHANGED')
    all_fitted=True
    for h,rows in samples.items():
        f=restore_fit(parameters['groups'][str(h)])
        products=tuple(sorted({r.product for r in rows}));dates=len({r.target for r in rows})
        enough=len(rows)>=spec.minimum_tasks and dates>=spec.minimum_dates and set(products)=={str(p.product_id) for p in data.products}
        if (f.tasks,f.dates,f.products)!=(len(rows),dates,products) or f.status!=('FITTED' if enough else 'NOT_FITTED'):
            raise ValueError('F2_PARAMETER_SUPPORT_CHANGED')
        if enough:
            low,lr=empirical_quantile(tuple(r.actual-r.lower for r in rows),F(1,4))
            high,ur=empirical_quantile(tuple(r.actual-r.upper for r in rows),F(3,4))
            if (f.lower_delta,f.upper_delta,f.lower_rank,f.upper_rank)!=(low,high,lr,ur):
                raise ValueError('F2_PARAMETER_ARITHMETIC_CHANGED')
        elif f.lower_delta or f.upper_delta or f.lower_rank or f.upper_rank:
            raise ValueError('F2_NOT_FITTED_ADJUSTMENT')
        all_fitted &= enough
    if parameters['status']!=('FITTED' if all_fitted else 'NOT_FITTED'):
        raise ValueError('F2_PARAMETER_STATUS_CHANGED')


def forecasts(data,predictions,native_evidence,parameters):
    """Keep package-native, before-policy and common-policy arrays distinct."""
    facts=facts_for(data);store=str(data.store_id);units={str(p.product_id):p.selling_unit for p in data.products}
    variants={k:[] for k in ('A_native','B_native','C_native','A_common','B_common','C0','C1')}
    audits=[]
    for row in predictions:
        r=dict(row);arm=r['arm'][0];origin=r['origin'];day=date.fromisoformat(r['target_date'])
        if r['store_id']!=store or r['product_id'] not in units or r['selling_unit']!=units[r['product_id']]:
            raise ValueError('F2_FORECAST_SCOPE_OR_UNIT')
        if (day-date.fromisoformat(origin)).days!=r['horizon']:raise ValueError('F2_FORECAST_ALIGNMENT')
        q=tuple(F(r[k]) for k in ('p25','p50','p75'))
        interval=None if r['cqr_lower'] is None else (F(r['cqr_lower']),F(r['cqr_upper']))
        variants[arm+'_native'].append(r)
        state=closure_state(facts,store,day,next_run(date.fromisoformat(origin),data.timezone))
        before=q;before_interval=interval;fit=None
        if arm=='C':
            e=native_evidence[origin]
            n=next(n for n in e['output']['native_predictions'] if n['product_id']==r['product_id'] and n['forecast_date']==r['target_date'])
            c=next(c for c in e['output']['cqr'] if c['product_id']==r['product_id'] and c['forecast_date']==r['target_date'])
            before=tuple(F(str(max(0.,float(v)+float(n['point_offset'])))) for v in n['repaired'])
            median=before[1];correction=F(c['correction'])
            before_interval=(min(max(F(0),before[0]-correction),median),max(before[2]+correction,median))
            # Verify the retained package's native closure output before replacing its policy.
            if bool(n['planned_closed'])!=(state=='CLOSED'):raise ValueError('F2_NATIVE_CALENDAR_POLICY_CONFLICT')
            expected_q=(F(0),)*3 if state=='CLOSED' else before
            expected_interval=(F(0),)*2 if state=='CLOSED' else before_interval
            if any(abs(a-b)>F(1,10**10) for a,b in zip(expected_q,q)) or any(abs(a-b)>F(1,10**10) for a,b in zip(expected_interval,interval)):
                raise ValueError('F2_NATIVE_STAGE_MISMATCH')
            # Retain the exact package CQR bytes; it is not an endpoint calibration output.
            fit=parameters[origin]
        common_q,common_interval=common_closure(before,before_interval,state)
        # Preserve exact package C values (float addition may differ by ULP in interval).
        if arm=='C':common_q,common_interval=q,interval
        def updated(qs,iv):
            return r|dict(zip(('p25','p50','p75'),qs))|dict(cqr_lower=None if iv is None else iv[0],cqr_upper=None if iv is None else iv[1])
        label='C0' if arm=='C' else arm+'_common'
        variants[label].append(updated(common_q,common_interval))
        audit=dict(origin=origin,target=r['target_date'],product=r['product_id'],horizon=r['horizon'],unit=r['selling_unit'],
            arm=arm,state=state,policy=POLICY_VERSION,policy_applications=1,before_policy=before,
            package_native=q,after_policy=common_q)
        if arm=='C':
            selected=restore_fit(fit['groups'][str(r['horizon'])])
            if fit['status']!='FITTED':selected=EndpointFit('NOT_FITTED','ORIGIN_NOT_FITTED',F(0),F(0),0,0,(),0,0)
            adjusted,clamps=correct_endpoints(before,selected)
            final,_=common_closure(adjusted,before_interval,state)
            if final[1]!=common_q[1]:raise ValueError('F2_P50_PRESERVATION_FAILED')
            variants['C1'].append(updated(final,common_interval))
            audit.update(endpoint_before_projection=(before[0]+selected.lower_delta,before[2]+selected.upper_delta),
                after_endpoint_before_closure=adjusted,C1=final,endpoint_clamps=clamps,
                cqr_policy='RETAINED_C0_CQR_NOT_REFIT',C1_policy_applications=1)
        audits.append(audit)
    return variants,audits


def metrics(variants,audits):
    states={(r['origin'],r['product'],r['target']):r['state'] for r in audits}
    groups=defaultdict(list);counts=Counter()
    for variant,rows in variants.items():
        for r in rows:
            counts[variant+'/'+r['partition']+'/'+r['mask']]+=1
            if r['actual'] is None:continue
            p=Point(r['product_id'],r['selling_unit'],r['origin'],r['target_date'],r['partition'],r['horizon'],F(r['actual']),
                tuple(F(r[q]) for q in ('p25','p50','p75')),
                None if r['cqr_lower'] is None else (F(r['cqr_lower']),F(r['cqr_upper'])),r['raw_crossing'])
            state=states[p.origin,p.product,p.target]
            for cohort in ('ALL',state):
                for dim,value in (('all','all'),('product',p.product),('horizon',str(p.horizon)),('product_horizon',p.product+'/'+str(p.horizon))):
                    groups[variant,p.partition,r['mask'],cohort,dim,value].append(p)
    result=[dict(variant=k[0],partition=k[1],mask=k[2],cohort=k[3],dimension=k[4],value=k[5],
        origins=len({p.origin for p in rows}),**score(tuple(rows))) for k,rows in sorted(groups.items())]
    return result,dict(counts)


def validation_decision(all_metrics,parameters):
    rows=[r for r in all_metrics if r['partition']=='validation' and r['mask']=='primary_known_false' and r['cohort']=='OPEN']
    index={(r['variant'],r['dimension'],r['value']):r for r in rows}
    a=index['C0','all','all'];b=index['C1','all','all']
    endpoint=lambda r:(r['pinball'][0]+r['pinball'][2])/2
    tails=lambda r:abs(r['below_p25']-F(1,4))+abs(r['above_p75']-F(1,4))
    regressions=[]
    for (variant,dim,value),r in index.items():
        if variant=='C1' and dim!='all' and endpoint(r)>endpoint(index['C0',dim,value]):
            regressions.append(dict(dimension=dim,value=value,C0=endpoint(index['C0',dim,value]),C1=endpoint(r)))
    support=all(p['status']=='FITTED' for origin,p in parameters.items() if origin in ('2026-06-10','2026-06-17'))
    conditions=dict(support=support,strict_endpoint_improvement=endpoint(b)<endpoint(a),
        lower_pinball_nonworse=b['pinball'][0]<=a['pinball'][0],upper_pinball_nonworse=b['pinball'][2]<=a['pinball'][2],
        tails_nonworse=tails(b)<=tails(a),no_product_horizon_cross_group_regression=not regressions,
        p50_exact=True)
    return dict(selected_endpoint_variant='C1' if all(conditions.values()) else 'C0',conditions=conditions,
        validation_regressions=regressions,scope='EXPLORATORY validation-only endpoint decision; evaluation does not select; no serving/promotion decision')
