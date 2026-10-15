"""Rebind an existing constant synthetic E2 artifact; ZERO fitting/training.

Only this known correctness artifact is accepted. New scope/runtime/publication
gets a new manifest identity; original bytes and historical experiments survive.
"""
from datetime import timedelta
import hashlib
import json
from pathlib import Path
from app.application.contracts.forecast_challenger import ChallengerArtifact,ChallengerInput,ArtifactFile
from app.application.forecast_challenger_serialization import canonical_bytes,challenger_digest
from app.infrastructure.forecast_challenger_runtime import current_runtime
from app.infrastructure.storage.forecast_challenger import ChallengerStorage

SOURCE='0c3c2b7539c0050bdf52fbfffa56f6ddac03c68654b3462ad1d2f2626896d936'


def rebind_fixture(storage,store,product,unit,instant,*,source_root=None):
    source_root=source_root or Path('runtime/challenger')
    source=ChallengerStorage(source_root).load_artifact(SOURCE)
    assert source.manifest.purpose=='synthetic_correctness'
    assert source.manifest.model_version=='e2-synthetic-constant-residual/1'
    runtime=current_runtime()
    products=[dict(product_id=product,selling_unit=unit)]
    files={f.name:(source.directory/f.name).read_bytes() for f in source.manifest.files}
    def update(name,**fields):
        files[name]=canonical_bytes(json.loads(files[name])|fields)
    version='f4-test-rebound-constant/1'
    update('category_mappings.json',store_key={str(store):0},product_key={str(product):0})
    update('training_manifest.json',scope=dict(store_id=store,products=products,timezone='Asia/Ho_Chi_Minh'),
        f4_declaration='Synthetic technical scope/runtime rebind of existing constant boosters. No fits, promotion, vintage proof or accuracy claim.',
        parent_artifact=SOURCE)
    update('point_corrector.json',model_id=version)
    update('calibrator.json',point_corrector_id=version)
    update('model_metadata.json',model_version=version,runtime_versions={'python_version':runtime.python,
        **{p.name+'_version':p.version for p in runtime.dependencies}})
    hashes={n:hashlib.sha256(b).hexdigest() for n,b in files.items() if n!='artifact_checksums.json'}
    files['artifact_checksums.json']=canonical_bytes({'algorithm':'sha256','files':hashes})
    data=source.manifest.model_dump(mode='python')|dict(store_id=store,products=products,runtime=runtime,
        model_version=version,published_at=instant,available_at=instant,
        postprocess_digest=challenger_digest('postprocess',{'point':hashes['point_corrector.json'],
            'cqr':hashes['calibrator.json'],'policy':'native_stack_weather_excluded/1'}),
        files=tuple(ArtifactFile(name=n,digest=hashlib.sha256(b).hexdigest()) for n,b in files.items()))
    manifest=ChallengerArtifact.model_validate(data)
    identity=storage.publish_artifact(manifest,files)
    cutoff=(instant+timedelta(hours=7)).date()-timedelta(days=1)
    start=cutoff-timedelta(days=59)
    observations=tuple(dict(store_id=store,product_id=product,sales_date=start+timedelta(days=i),
        quantity='0' if i==0 else '10',selling_unit=unit,is_stockout=True if i==0 else None if i==2 else False,
        available_at=instant,source='F4_COMPLETE_SYNTHETIC_OBSERVATION_DECLARATION/1') for i in range(60))
    return ChallengerInput(request=dict(store_id=store,product_ids=(product,),history_start_date=start,cutoff_date=cutoff),
        timezone='Asia/Ho_Chi_Minh',inference_at=instant+timedelta(seconds=1),products=products,observations=observations,
        forecast_dates=tuple(cutoff+timedelta(days=i) for i in range(1,8)),artifact_identity=identity,
        calendar=tuple(dict(store_id=store,day=start+timedelta(days=i),closed=i==66,holiday=False,
            available_at=instant,source='F4_EXPLICIT_SYNTHETIC_CALENDAR/1') for i in range(67)))
