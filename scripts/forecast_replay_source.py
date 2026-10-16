"""Explicit trusted-Git source capture for read-only historical benchmark replay."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile


def digest(value):
    raw=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
    return hashlib.sha256(b'shelfcash.readonly-replay-source.v1\n'+raw).hexdigest()


def git_sources(root:Path,commit:str):
    if len(commit)!=40 or any(c not in '0123456789abcdef' for c in commit):raise ValueError('INVALID_SOURCE_COMMIT')
    result=subprocess.run(['git','archive',commit,'app','scripts','tests/fixtures'],
        cwd=root,check=True,capture_output=True)
    with tarfile.open(fileobj=io.BytesIO(result.stdout)) as archive:
        return {m.name:archive.extractfile(m).read() for m in archive.getmembers()
                if m.isfile() and Path(m.name).suffix in ('.py','.json')}


def capture(root:Path,commit:str,experiment:str):
    from app.infrastructure.forecast_benchmark_storage import BenchmarkStorage
    storage=BenchmarkStorage(root/'runtime/challenger/benchmarks')
    directory=storage.path('experiments',experiment)
    environment=directory/'environment.json'
    files={}
    for name,committed in git_sources(root,commit).items():
        raw=(root/name).read_bytes()
        if raw.replace(b'\r\n',b'\n')!=committed.replace(b'\r\n',b'\n'):
            raise ValueError('SOURCE_NOT_AT_REQUESTED_COMMIT:'+name)
        files[name]=raw
    manifest=dict(schema_version=1,git_commit=commit,experiment=experiment,
        environment_sha256=hashlib.sha256(environment.read_bytes()).hexdigest(),
        files={name:hashlib.sha256(raw).hexdigest() for name,raw in files.items()})
    identity=digest(manifest)
    target=root/'runtime/challenger/replay-sources'/identity
    for name,raw in files.items():
        path=target/name
        if path.exists() and path.read_bytes()!=raw:raise ValueError('IMMUTABLE_SOURCE_SNAPSHOT_CONFLICT')
        path.parent.mkdir(parents=True,exist_ok=True)
        if not path.exists():path.write_bytes(raw)
    meta=json.dumps(manifest,sort_keys=True,ensure_ascii=False,indent=2).encode()
    path=target/'source.json'
    if path.exists() and path.read_bytes()!=meta:raise ValueError('IMMUTABLE_SOURCE_SNAPSHOT_CONFLICT')
    if not path.exists():path.write_bytes(meta)
    verify(root,target,experiment)
    return target


def verify(root:Path,snapshot:Path,experiment:str):
    manifest=json.loads((snapshot/'source.json').read_bytes())
    if digest(manifest)!=snapshot.name or manifest['experiment']!=experiment:raise ValueError('HISTORICAL_SOURCE_IDENTITY_MISMATCH')
    environment=root/'runtime/challenger/benchmarks/experiments'/experiment/'environment.json'
    if hashlib.sha256(environment.read_bytes()).hexdigest()!=manifest['environment_sha256']:
        raise ValueError('HISTORICAL_ENVIRONMENT_CHANGED')
    committed=git_sources(root,manifest['git_commit'])
    if set(committed)!=set(manifest['files']):raise ValueError('HISTORICAL_SOURCE_FILE_SET')
    actual={p.relative_to(snapshot).as_posix() for p in snapshot.rglob('*') if p.is_file() and p.suffix in ('.py','.json')}
    if actual!=set(manifest['files'])|{'source.json'}:raise ValueError('HISTORICAL_SOURCE_FILE_SET')
    for name,expected in manifest['files'].items():
        path=snapshot/name
        if path.is_symlink() or not path.resolve().is_relative_to(snapshot.resolve()):raise ValueError('UNSAFE_HISTORICAL_SOURCE')
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('HISTORICAL_SOURCE_HASH_MISMATCH:'+name)
        if raw.replace(b'\r\n',b'\n')!=committed[name].replace(b'\r\n',b'\n'):
            raise ValueError('HISTORICAL_SOURCE_GIT_MISMATCH:'+name)
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit',required=True)
    parser.add_argument('--experiment',required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    print(json.dumps(dict(snapshot=str(capture(root,args.commit,args.experiment)))))


if __name__=='__main__':main()
