"""Compare current wire schemas with the retained original 2026-10-10 baseline.

No database/provider access. Generated outputs belong in ignored runtime only.
Archive source and baseline hashes are in the compatibility changelog.
"""
import hashlib
import json
from pathlib import Path

from app.config import Settings
from app.main import create_app

ROOT=Path(__file__).resolve().parents[1]
BASELINE_SHA="238959dd16307ebd691834d2a679f7f80134495bbe99c56f29f7835f39bab6fd"
BASELINE_PATH=ROOT/"tests/fixtures/openapi_20261010.json"
BASELINE_API_SHA="04ee429440efa23a5c74035d01c8c1f63df7d231cee54705d848856592879d63"


def load_baseline():
    data=BASELINE_PATH.read_bytes()
    if hashlib.sha256(data).hexdigest()!=BASELINE_API_SHA:
        raise ValueError("Original OpenAPI baseline integrity mismatch")
    return json.loads(data)


def snapshot():
    old=load_baseline()
    current=create_app(Settings(_env_file=None)).openapi()
    def operations(spec):
        return {value["operationId"]:(method,path,value) for path,methods in spec["paths"].items()
                for method,value in methods.items() if method in {"get","post","put","patch","delete","head","options"}}
    before,after=operations(old),operations(current)
    old_s,new_s=old["components"]["schemas"],current["components"]["schemas"]
    diff=dict(baseline_sha256=BASELINE_SHA,baseline_openapi_sha256=BASELINE_API_SHA,baseline_operations=len(before),current_operations=len(after),
        added_operations=sorted(after.keys()-before.keys()),removed_operations=sorted(before.keys()-after.keys()),
        changed_operations=sorted(k for k in before.keys()&after.keys() if before[k]!=after[k]),
        added_schemas=sorted(new_s.keys()-old_s.keys()),removed_schemas=sorted(old_s.keys()-new_s.keys()),
        changed_schemas=sorted(k for k in old_s.keys()&new_s.keys() if old_s[k]!=new_s[k]))
    directory=ROOT/"runtime/verification/openapi";directory.mkdir(parents=True,exist_ok=True)
    for name,value in (("openapi.json",current),("openapi_diff.json",diff)):
        (directory/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    rows=["# Current runtime routes", "", "| Operation | Method | Path |", "| --- | --- | --- |"]
    rows += [f"| {key} | {method.upper()} | `{path}` |" for key,(method,path,_) in sorted(after.items())]
    (directory/"routes.md").write_text("\n".join(rows)+"\n",encoding="utf-8")
    print(json.dumps({k:diff[k] for k in ("baseline_operations","current_operations","added_operations","changed_operations","removed_operations")}))
    return diff


if __name__=="__main__":
    snapshot()
