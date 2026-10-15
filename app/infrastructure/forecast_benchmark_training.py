"""Explicit bounded E3 fits: host baseline/LightGBM and native residual/point/CQR."""
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from time import monotonic

from app.application.contracts.forecast_benchmark import ARMS, ArmCheckpoint, BenchmarkDataset, BenchmarkOrigin, BenchmarkPlan, BenchmarkPrediction
from app.application.contracts.forecast_challenger import ArtifactFile, ChallengerArtifact, ChallengerInput, FitWindow
from app.application.forecast_benchmark_admission import at_origin, calendar_at_origin, holdout_dates, next_run
from app.application.forecast_challenger_serialization import canonical_bytes, challenger_digest
from app.application.use_cases.forecast_challenger import ForecastChallenger
from app.infrastructure.forecast_challenger_runtime import current_runtime
from app.infrastructure.storage.forecast_challenger import ChallengerStorage
from app.infrastructure.forecast_benchmark_features import prepared_at, host_rows, native_frame, native_training_table, postprocess_tasks
from app.infrastructure.forecast_benchmark_storage import BenchmarkStorage, FitBudget, training_source_identity


def fit_identity(data: BenchmarkDataset, plan: BenchmarkPlan, task: BenchmarkOrigin, arm: str, config) -> str:
    prefix = {'observations':at_origin(data,task.origin), 'store_id':data.store_id, 'products':data.products,
              'timezone':data.timezone, 'source_revision':data.source_revision}
    # Include future known calendar too: inference uses explicit D+1..D+7 facts.
    from datetime import timedelta
    prefix['calendar'] = tuple(c for c in data.calendar if c.day <= task.origin+timedelta(days=7) and
                               c.available_at <= next_run(task.origin,data.timezone))
    return challenger_digest('fit', {'prefix':prefix, 'task':task, 'arm':arm,'configuration':config,
        'holdout_fit_labels':sorted(holdout_dates(plan)), 'training_source':training_source_identity(),
        'runtime':current_runtime()})


def raw_records(data: BenchmarkDataset, task: BenchmarkOrigin, arm: str, result, *, intervals=(), crossings=()):
    units={p.product_id:p.selling_unit for p in data.products}
    cqr={(p.product_id,p.forecast_date):p for p in intervals}
    return tuple(BenchmarkPrediction(arm=arm,store_id=data.store_id,product_id=p.product_id,
        selling_unit=units[p.product_id],origin=task.origin,partition=task.partition,target_date=p.forecast_date,
        horizon=(p.forecast_date-task.origin).days,actual=None,stockout=None,mask='missing',
        p25=p.p25,p50=p.p50,p75=p.p75,
        cqr_lower=cqr[p.product_id,p.forecast_date].lower if cqr else None,
        cqr_upper=cqr[p.product_id,p.forecast_date].upper if cqr else None,
        raw_crossing=(p.product_id,p.forecast_date) in crossings) for p in result.predictions)


def train_host(data, plan, task, arm, guard: FitBudget, directory: Path, storage: BenchmarkStorage):
    import lightgbm as lgb
    import numpy as np
    from app.application.use_cases.forecast_baseline import run_historical_quantile_baseline
    from app.infrastructure.forecast_model import QuantileModel, _matrix, predict_quantiles
    from app.application.contracts.forecast_model import FEATURE_NAMES
    from app.application.forecast_serialization import serialize_prepared
    started=monotonic()
    captured=prepared_at(data, task.origin)
    if arm==ARMS[0]:
        model_capture=prepared_at(data,task.origin,exclude=holdout_dates(plan))
        result=run_historical_quantile_baseline(model_capture)
        trained=monotonic()-started
        return raw_records(data,task,arm,result), trained, Decimal(0), None, 0, None
    rows=host_rows(data,task.origin,plan,guard)
    matrix=_matrix(rows.features)
    targets=np.asarray([float(v) for v in rows.targets])
    boosters=[]
    for q in (.25,.50,.75):
        guard.booster()
        dataset=lgb.Dataset(matrix,label=targets,feature_name=list(FEATURE_NAMES),categorical_feature=['product_code'])
        booster=lgb.train(dict(objective='quantile',alpha=q,num_threads=1,deterministic=True,
            force_col_wise=True,seed=1729,num_leaves=7,learning_rate=.05,min_data_in_leaf=5,verbosity=-1),
            dataset,num_boost_round=40,callbacks=[guard.callback])
        boosters.append(booster)
    serialized=serialize_prepared(captured)
    files={f'p{q}.txt':b.model_to_string() for q,b in zip((25,50,75),boosters)}
    storage.retain(directory,'host-model.json', {'prepared':json.loads(serialized.canonical_json),
        'input_digest':serialized.digest,'files':files,'training_keys':rows.keys,
        'holdout_quarantined':rows.quarantined_labels,'training_source':training_source_identity()})
    trained=monotonic()-started
    inference=monotonic()
    result,crossings,negative=predict_quantiles(QuantileModel(captured,tuple(boosters)),captured)
    elapsed=monotonic()-inference
    storage.retain(directory,'host-diagnostics.json', {'negative_clamps':negative})
    return raw_records(data,task,arm,result,crossings=crossings), trained, elapsed, challenger_digest('host-artifact',files), sum(len(v.encode()) for v in files.values()), None


def train_challenger(data, plan, task, config_spec, guard: FitBudget, directory: Path,
                     storage: BenchmarkStorage, artifacts: ChallengerStorage):
    import lightgbm as lgb
    import numpy as np
    from shelfcash_forecast.config import ForecastConfig
    from shelfcash_forecast.features.specification import CategoryEncoder, MODEL_FEATURES, CATEGORICAL_MODEL_COLUMNS
    from shelfcash_forecast.models.quantile_models import QuantileModelBundle
    from shelfcash_forecast.calibration.point import fit_point_corrector
    from shelfcash_forecast.calibration.cqr import fit_cqr_calibrator
    started=monotonic()
    config=ForecastConfig.from_dict(config_spec['forecast_config'])
    encoder=CategoryEncoder({'store_key':{str(data.store_id):0},
        'product_key':{str(p.product_id):i for i,p in enumerate(data.products)}})
    table,quarantined=native_training_table(data,task.train_end,plan,config,encoder,guard)
    matrix=table[MODEL_FEATURES].astype(float)
    for name in CATEGORICAL_MODEL_COLUMNS:
        matrix[name]=matrix[name].astype('int32')
    boosters={}
    params=dict(config.lightgbm_params)
    rounds=params.pop('n_estimators')
    params['num_threads']=params.pop('n_jobs')
    for q in (.25,.50,.75):
        guard.booster()
        booster=lgb.train(dict(params,objective='quantile',alpha=q),
            lgb.Dataset(matrix,label=table['target'].to_numpy(dtype=float),feature_name=MODEL_FEATURES,
                        categorical_feature=CATEGORICAL_MODEL_COLUMNS),
            num_boost_round=rounds,callbacks=[guard.callback])
        boosters[q]=booster
    model=QuantileModelBundle(boosters,list(MODEL_FEATURES),list(CATEGORICAL_MODEL_COLUMNS),
                             target_strategy='seasonal_residual_signed',residual_blend_lambda=1.0)
    storage.retain(directory,'native-booster-fit.json', {'configuration':config_spec,
        'input_identity':directory.name,'training_source':training_source_identity(),
        'models':{str(q):b.model_to_string() for q,b in boosters.items()}})
    storage.retain(directory,'training-table.json',json.loads(table.to_json(orient='records',date_format='iso')))
    model_version='e3-'+directory.name[:24]
    point_frame,point_audit=postprocess_tasks(data,task.point_start,task.point_end,task.train_end,
                                             plan,config,encoder,model,guard)
    guard.calibration()
    point=fit_point_corrector(point_frame,method=config_spec['point_method'],
        minimum_group_tasks=config_spec['minimum_group_tasks'],
        minimum_group_distinct_target_dates=config_spec['minimum_group_distinct_target_dates'],
        shrinkage_strength=config_spec['shrinkage_strength'],model_id=model_version,
        actual_known_at_cutoff=next_run(task.point_end,data.timezone).isoformat(), availability_timezone=data.timezone,
        calibration_target_semantics='observed_sales_non_stockout')
    calibration_frame,calibration_audit=postprocess_tasks(data,task.calibration_start,task.calibration_end,
        task.point_end,plan,config,encoder,model,guard,point=point)
    guard.calibration()
    calibrator=fit_cqr_calibrator(calibration_frame,config.nominal_coverage,config.minimum_calibration_samples,
        calibration_target_semantics='observed_sales_non_stockout',point_corrector_id=model_version)
    fitted=datetime.now(timezone.utc)
    runtime=current_runtime()
    train_window=FitWindow(start=table['target_date'].min().date(),end=table['target_date'].max().date(),
                          labels_available_at=next_run(task.train_end,data.timezone))
    point_window=FitWindow(start=date.fromisoformat(point.fit_target_start),end=date.fromisoformat(point.fit_target_end),
                          labels_available_at=next_run(task.point_end,data.timezone))
    cal_window=FitWindow(start=date.fromisoformat(calibrator.fit_target_start),end=date.fromisoformat(calibrator.fit_target_end),
                        labels_available_at=next_run(task.calibration_end,data.timezone))
    native_json={
        'feature_schema.json':{'schema_version':'3.0','features':MODEL_FEATURES,'categorical_features':CATEGORICAL_MODEL_COLUMNS,
                               'target_strategy':'seasonal_residual_signed','residual_blend_lambda':1.0},
        'preprocessing_config.json':config.to_dict(),'category_mappings.json':encoder.to_dict(),
        'point_corrector.json':point.to_dict(),'calibrator.json':calibrator.to_dict(),
        'model_metadata.json':{'model_version':model_version,'training_label_cutoff':str(train_window.end),
            'point_fit_label_cutoff':str(point_window.end),'calibration_label_cutoff':str(cal_window.end),
            'artifact_fitted_at':fitted.isoformat(),'promotion_status':'trained_candidate','production_available_at':None,
            'holdout_status':'SYNTHETIC_ONLY' if data.classification=='SYNTHETIC' else 'EXPOSED' if data.classification=='REAL_EXPOSED' else 'UNSEEN',
            'runtime_versions':{'python_version':runtime.python,**{p.name+'_version':p.version for p in runtime.dependencies}}},
        'training_manifest.json':{'scope':{'store_id':data.store_id,'products':data.products,'timezone':data.timezone},
            'training_source':training_source_identity(),'fit_input_identity':directory.name,
            'availability_basis':data.availability_basis,'source_revision':data.source_revision,'limitations':data.limitations,
            'protocol_digest':plan.protocol_digest,'planned_windows':task,'holdout_fit_policy':plan.holdout_fit_policy,
            'training_holdout_quarantined':quarantined,'point_audit':point_audit,'calibration_audit':calibration_audit,
            'booster_rows':len(table),'booster_distinct_target_dates':table['target_date'].nunique(),
            'point_tasks':len(point_frame),'calibration_tasks':len(calibration_frame),'rounds':rounds,
            'fit_implementation':'lightgbm_train_explicit_quantile/1','mapped_parameters':params},
    }
    files={f'model_q{int(q*100)}.txt':b.model_to_string().encode() for q,b in boosters.items()}
    files.update({name:canonical_bytes(v) for name,v in native_json.items()})
    hashes={name:hashlib.sha256(v).hexdigest() for name,v in files.items()}
    files['artifact_checksums.json']=canonical_bytes({'algorithm':'sha256','files':hashes})
    manifest=ChallengerArtifact(model_version=model_version,purpose='synthetic_correctness' if data.classification=='SYNTHETIC' else 'research_candidate',
        holdout_status=native_json['model_metadata.json']['holdout_status'],promotion_status='trained_candidate',production_available_at=None,
        store_id=data.store_id,products=data.products,timezone=data.timezone,runtime=runtime,training=train_window,point_fit=point_window,
        calibration=cal_window,fitted_at=fitted,published_at=fitted,available_at=fitted,publication_basis='local_snapshot_admission',
        config_digest=hashes['preprocessing_config.json'],feature_digest=hashes['feature_schema.json'],
        postprocess_digest=challenger_digest('postprocess',{'point':hashes['point_corrector.json'],'cqr':hashes['calibrator.json'],
                                                          'policy':'native_stack_weather_excluded/1'}),
        files=tuple(ArtifactFile(name=name,digest=hashlib.sha256(v).hexdigest()) for name,v in files.items()))
    identity=artifacts.publish_artifact(manifest,files)
    storage.retain(directory,'point-tasks.json',json.loads(point_frame.to_json(orient='records',date_format='iso')))
    storage.retain(directory,'calibration-tasks.json',json.loads(calibration_frame.to_json(orient='records',date_format='iso')))
    value=ChallengerInput(request={'store_id':data.store_id,'product_ids':tuple(p.product_id for p in data.products),
        'history_start_date':min(o.sales_date for o in at_origin(data,task.origin)),'cutoff_date':task.origin},
        timezone=data.timezone,inference_at=datetime.now(timezone.utc),products=data.products,observations=at_origin(data,task.origin),
        calendar=calendar_at_origin(data,task.origin),forecast_dates=prepared_at(data,task.origin).forecast_dates,artifact_identity=identity)
    trained=monotonic()-started
    inference=monotonic()
    result=ForecastChallenger(artifacts,enabled=True).execute(value)
    elapsed=monotonic()-inference
    crosses=tuple((p.product_id,p.forecast_date) for p in result.evidence.output.native_predictions if p.raw_crossing)
    records=raw_records(data,task,ARMS[2],result.evidence.output.forecast,intervals=result.evidence.output.cqr,crossings=crosses)
    storage.retain(directory,'native-inference.json',result.evidence)
    return records,trained,elapsed,identity,sum(len(v) for v in files.values()),result.evidence.cache_identity


def fit_arm(data,plan,task,arm,config,guard,storage:BenchmarkStorage,artifacts:ChallengerStorage):
    identity=fit_identity(data,plan,task,arm,config)
    directory=storage.path('fits',identity)
    old=storage.load(directory,'checkpoint.json')
    if old is not None:
        checkpoint=ArmCheckpoint.model_validate(old)
        return checkpoint,True
    start=monotonic()
    if arm==ARMS[2]:
        rows,trained,inference,artifact,size,replay=train_challenger(data,plan,task,config,guard,directory,storage,artifacts)
    else:
        rows,trained,inference,artifact,size,replay=train_host(data,plan,task,arm,guard,directory,storage)
    checkpoint=ArmCheckpoint(arm=arm,origin=task.origin,identity=identity,status='COMPLETED',reason=None,predictions=rows,
        artifact_identity=artifact,input_digest=identity,training_seconds=Decimal(str(trained)),inference_seconds=Decimal(str(inference)),
        artifact_bytes=size,replay_identity=replay)
    guard.check()
    storage.retain(directory,'checkpoint.json',checkpoint)
    return checkpoint,False
