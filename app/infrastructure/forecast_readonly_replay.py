"""Current verifier dispatches only explicitly verified historical source, with no writes."""
import json
from pathlib import Path
import subprocess
import sys


def replay(root:Path,experiment:str,*,dedicated:bool=False) -> dict:
    from app.application.forecast_challenger_validation import require
    from scripts.forecast_replay_source import verify
    require(len(experiment)==64 and all(c in '0123456789abcdef' for c in experiment),'INVALID_BENCHMARK_KEY')
    candidates=[]
    for source in (root/'runtime/challenger/replay-sources').glob('*/source.json'):
        if json.loads(source.read_bytes()).get('experiment')==experiment:candidates.append(source.parent)
    if len(candidates)!=1:raise ValueError('EXPLICIT_UNIQUE_HISTORICAL_SOURCE_REQUIRED')
    snapshot=candidates[0]
    manifest=verify(root,snapshot,experiment)
    command=[sys.executable,'-B',str(root/'scripts/forecast_replay_worker.py'),
             '--workspace',str(root),'--snapshot',str(snapshot),'--experiment',experiment]
    if dedicated:command.append('--dedicated')
    result=subprocess.run(command,cwd=snapshot,capture_output=True,text=True,encoding='utf-8',timeout=120)
    if result.returncode:raise ValueError('READONLY_REPLAY_FAILED:'+result.stderr[-3000:])
    report=json.loads(result.stdout)
    if report['execution_source_commit']!=manifest['git_commit'] or report['historical_source_identity']!=snapshot.name:
        raise ValueError('REPLAY_SOURCE_RECEIPT_MISMATCH')
    import hashlib
    from app.application.forecast_challenger_serialization import challenger_digest
    from app.infrastructure.forecast_benchmark_storage import BenchmarkStorage
    report['dispatcher_source_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    report['source_validator_sha256']=hashlib.sha256((root/'scripts/forecast_replay_source.py').read_bytes()).hexdigest()
    output=BenchmarkStorage(root/'runtime/challenger/f1')
    target=output.path('replays',challenger_digest('readonly-replay',report))
    output.retain(target,'replay.json',report)
    report['verification_receipt']=str(target/'replay.json')
    return report
