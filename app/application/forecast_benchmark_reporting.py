"""Paired scoring and validation-only selection; no training/model/DB access."""
from collections import Counter
from decimal import Decimal
from datetime import datetime, timezone

from app.application.contracts.forecast_benchmark import ARMS, ArmCheckpoint, BenchmarkDataset, BenchmarkPlan, BenchmarkPrediction
from app.domain.forecasting.benchmark_metrics import Score, metrics


def attach_targets(data: BenchmarkDataset, checkpoint: ArmCheckpoint) -> tuple[BenchmarkPrediction,...]:
    scored_at=datetime.now(timezone.utc)
    actuals={(o.product_id,o.sales_date):o for o in data.observations if o.available_at <= scored_at}
    values=[]
    for prediction in checkpoint.predictions:
        observation=actuals.get((prediction.product_id,prediction.target_date))
        actual=None if observation is None else observation.quantity
        stockout=None if observation is None else observation.is_stockout
        mask='missing' if observation is None else 'censored_lower_bound' if stockout is True else 'primary_known_false' if stockout is False else 'supplementary_unknown'
        record=prediction.model_dump(mode='python')
        record.update(actual=actual,stockout=stockout,mask=mask)
        values.append(BenchmarkPrediction.model_validate(record))
    return tuple(values)


def summary(data: BenchmarkDataset, plan: BenchmarkPlan, checkpoints: tuple[ArmCheckpoint,...], *, complete:bool) -> dict:
    arms=plan.configuration_ids
    rows=tuple(p for c in checkpoints for p in attach_targets(data,c))
    task=lambda r:(r.store_id,r.product_id,r.origin,r.horizon)
    keys={arm:{task(r) for r in rows if r.arm==arm} for arm in arms}
    common=set.intersection(*(keys[a] for a in arms))
    population=len(plan.tasks)*len(data.products)*7
    paired=tuple(r for r in rows if task(r) in common)
    group_metrics=[]
    for arm in arms:
        for partition in ('validation','holdout'):
            for mask in ('primary_known_false','supplementary_unknown','censored_lower_bound','missing'):
                subset=tuple(r for r in paired if (r.arm,r.partition,r.mask)==(arm,partition,mask))
                groups=[('all',None,subset)]
                groups += [('product',str(p.product_id),tuple(r for r in subset if r.product_id==p.product_id)) for p in data.products]
                groups += [('horizon',h,tuple(r for r in subset if r.horizon==h)) for h in range(1,8)]
                groups += [('product_horizon',f'{p.product_id}/{h}',tuple(r for r in subset if r.product_id==p.product_id and r.horizon==h))
                           for p in data.products for h in range(1,8)]
                groups += [('unit',u,tuple(r for r in subset if r.selling_unit==u)) for u in sorted({p.selling_unit for p in data.products})]
                for dimension,value,group in groups:
                    scores=tuple(Score(str(r.store_id),str(r.product_id),r.target_date,r.selling_unit,r.actual,
                        (r.p25,r.p50,r.p75),None if r.cqr_lower is None else (r.cqr_lower,r.cqr_upper),r.raw_crossing)
                        for r in group if r.actual is not None)
                    group_metrics.append({'arm':arm,'partition':partition,'mask':mask,'dimension':dimension,
                        'value':value,'available_tasks':len(group),**metrics(scores)})
    aggregate={(m['arm'],m['partition']):m for m in group_metrics if m['dimension']=='all' and m['mask']=='primary_known_false'}
    losses={a:aggregate[a,'validation']['mean_pinball'] for a in arms}
    selected=None
    validation_origins={a:len({r.origin for r in paired if r.arm==a and
                              r.partition=='validation' and r.mask=='primary_known_false'}) for a in arms}
    if complete and all(v is not None for v in losses.values()) and all(n>=2 for n in validation_origins.values()):
        selected=min(arms,key=lambda a:(losses[a],arms.index(a)))
    aggregate_leader=selected
    if plan.harness_version=='causal_benchmark/3': selected=None
    primary_counts={p:aggregate[ARMS[0],p]['distinct_outcomes'] for p in ('validation','holdout')}
    origin_counts={p:len({r.origin for r in paired if r.arm==ARMS[0] and r.partition==p and r.mask=='primary_known_false'})
                   for p in ('validation','holdout')}
    numeric_gate=(complete and len(common)==population and all(n>=28 for n in primary_counts.values())
                  and all(n>=2 for n in origin_counts.values()))
    improvement=ARMS[2] in arms and all(aggregate[ARMS[2],p]['mean_pinball'] is not None and all(
        aggregate[ARMS[2],p]['mean_pinball'] < aggregate[a,p]['mean_pinball'] for a in arms[:2])
        for p in ('validation','holdout')) if numeric_gate else False
    return {'schema_version':3 if plan.harness_version=='causal_benchmark/3' else 2 if plan.harness_version=='causal_benchmark/2' else 1,'comparison_arms':arms,
        'challenger_evidence':ARMS[2] in arms,
        'wape_denominator_policy':'sum eligible observed actual quantities on paired mask; null at zero denominator','status':'EXPLORATORY' if plan.harness_version!='causal_benchmark/1' and complete else 'SYNTHETIC_CORRECTNESS' if complete and data.classification=='SYNTHETIC'
            else 'EXPLORATORY' if complete else 'INCOMPLETE',
        'real_benchmark':'REAL_BENCHMARK_BLOCKED' if data.classification=='SYNTHETIC' else 'EXPLORATORY' if data.classification=='REAL_EXPOSED' else 'EVALUATED_UNSEEN_NOT_PROMOTED',
        'population_tasks_per_arm':population,'output_coverage':{a:len(keys[a]) for a in arms},
        'paired_tasks':len(common),'paired_coverage_fraction':Decimal(len(common))/population,
        'distinct_outcomes':len({(r.store_id,r.product_id,r.target_date) for r in paired}),
        'distinct_dates':len({r.target_date for r in paired}),
        'masks':dict(Counter(r.mask for r in paired if r.arm==ARMS[0])),
        'exclusions':[{'arm':c.arm,'origin':c.origin,'status':c.status,'reason':c.reason} for c in checkpoints if c.status!='COMPLETED'],
        'selected_by_validation_only':selected,'primary_distinct_outcomes':primary_counts,
        'validation_aggregate_leader':aggregate_leader,
        'selection_policy':'REPORT_PRODUCT_TRADEOFFS_NO_AUTOMATIC_WINNER' if plan.harness_version=='causal_benchmark/3' else 'VALIDATION_MEAN_PINBALL',
        'primary_origin_counts':origin_counts,
        'validation_origins_with_primary_targets':validation_origins,
        'raw_crossing_tasks':{a:sum(r.raw_crossing for r in rows if r.arm==a) for a in arms},
        'final_crossing_count':0 if complete else None,'nonfinite_final_predictions':0 if complete else None,
        'technical_failure_count':sum(c.status=='TECHNICAL_FAILURE' for c in checkpoints),
        'accuracy_numeric_gate':numeric_gate,'challenger_strict_improvement':improvement,
        'promotion_evidence':'INSUFFICIENT_EVIDENCE','production':'LOCKED',
        'mixed_unit_interpretation':'mathematical equal-task scores only; not monetary or business accuracy guarantee',
        'data_classification':data.classification,'availability_basis':data.availability_basis,'limitations':data.limitations,
        'training_seconds':sum(c.training_seconds for c in checkpoints),'inference_seconds':sum(c.inference_seconds for c in checkpoints),
        'arm_execution':{a:dict(completed=sum(c.status=='COMPLETED' for c in checkpoints if c.arm==a),
            training_seconds=sum(c.training_seconds for c in checkpoints if c.arm==a),
            inference_seconds=sum(c.inference_seconds for c in checkpoints if c.arm==a),
            fallback_count=0,method=a) for a in arms},
        'artifact_bytes':sum(c.artifact_bytes for c in checkpoints),'metrics':group_metrics}
