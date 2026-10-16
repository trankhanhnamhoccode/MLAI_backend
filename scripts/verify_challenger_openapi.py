"""Read-only local-main snapshot OpenAPI comparison; no checkout/fetch/worktree."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'runtime/challenger/f4/openapi'


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    base=subprocess.check_output(['git','rev-parse','main'],cwd=ROOT,text=True).strip()
    target=OUT/('source-'+base)
    target.mkdir(exist_ok=True)
    archive=subprocess.check_output(['git','archive','--format=tar',base],cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(archive)) as source:
        for member in source.getmembers():
            if not (target/member.name).resolve().is_relative_to(target.resolve()) or member.issym() or member.islnk():
                raise ValueError('Unsafe archive member')
        source.extractall(target,filter='data')
    command="import json;from app.main import app;print(json.dumps(app.openapi(),sort_keys=True,separators=(',',':')))"
    results={}
    for name,directory in [('main',target),('f4',ROOT)]:
        env=os.environ.copy();env.update(PYTHONPATH=str(directory),PYTHONDONTWRITEBYTECODE='1')
        raw=subprocess.check_output([sys.executable,'-B','-c',command],cwd=directory,env=env)
        value=json.loads(raw);payload=json.dumps(value,sort_keys=True,separators=(',',':')).encode()
        (OUT/(name+'.json')).write_bytes(payload)
        results[name]=dict(sha256=hashlib.sha256(payload).hexdigest(),operations=sum(method in {'get','put','post','delete','patch','options','head'} for p in value['paths'].values() for method in p))
    report=dict(base=base,source_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        unchanged=results['main']==results['f4'],schemas=results)
    (OUT/'comparison.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report))


if __name__=='__main__':main()
