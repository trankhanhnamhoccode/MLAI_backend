"""Read-only DEMO workbook admission, never training or Planning.

python -m scripts.prepare_demo_benchmark --uploads runtime/uploads
python -m scripts.prepare_demo_benchmark --uploads runtime/uploads --declarations <explicit-declarations.json>
Schema template: tests/fixtures/forecast_engine/demo_admission.template.json
"""
import argparse
import hashlib
import json
from pathlib import Path

from app.application.contracts.demo_workbooks import AdmissionDeclarations
from app.application.demo_workbook_normalization import normalize_demo
from app.application.demo_workbook_admission import assess
from app.application.forecast_challenger_serialization import challenger_digest,canonical_bytes
from app.application.use_cases.forecast_benchmark import load_protocol
from app.infrastructure.demo_workbook_reader import discover_workbooks, read_workbook
from app.infrastructure.forecast_benchmark_storage import BenchmarkStorage

ROOT=Path(__file__).resolve().parents[1]


def inventory_runtime(directory:Path,root:Path):
    """Inventory all candidate bytes before role selection, including unknown files."""
    from app.application.demo_workbook_normalization import day
    rows=[]
    for path in sorted(directory.rglob('*')):
        if not path.is_file() or path.suffix.lower() not in ('.xlsx','.csv','.tsv'): continue
        raw=path.read_bytes()
        if path.suffix.lower()=='.xlsx':
            book=read_workbook(path)
            row=book.metadata
            for sheet,metadata in zip(book.parsed.sheets,row['sheets'],strict=True):
                metadata['preamble_and_headers']=[dict(row=r.row_number,cells=[c.raw for c in r.cells]) for r in sheet.rows[:3]]
                dates=[]
                for r in sheet.rows:
                    if r.row_number<=3: continue
                    value=next((c for c in r.cells if c.column_index==0),None)
                    if value is None or value.formula or value.raw is None: continue
                    try: dates.append(day(value.raw,book.parsed.excel_date_system))
                    except ValueError: pass
                metadata['date_column_A']=dict(first=min(dates,default=None),last=max(dates,default=None),distinct=len(set(dates)))
        else:
            row=dict(path=str(path.resolve()),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),role='unclassified',format=path.suffix)
        if hashlib.sha256(path.read_bytes()).digest()!=hashlib.sha256(raw).digest(): raise ValueError('RAW_HASH_CHANGED')
        rows.append(row)
    storage=BenchmarkStorage(root/'runtime/challenger/dataset-admission')
    identity=challenger_digest('runtime-inventory-v2',rows)
    target=storage.path('inventories',identity)
    storage.retain(target,'inventory.json',rows)
    return target,rows


def prepare(uploads:Path,root:Path,declarations:AdmissionDeclarations):
    inventory_path,_=inventory_runtime(uploads,root)
    books=discover_workbooks(uploads)
    normalized,issues=normalize_demo(books,declarations.timezone)
    if declarations.observation_availability!='UNDECLARED' and declarations.source_revision!=normalized.source_revision:
        raise ValueError('DECLARATION_DATASET_HASH_MISMATCH')
    protocol=load_protocol(root)
    manifest,tables,dataset,plan=assess(normalized,books,declarations,issues,protocol)
    source_files=('scripts/prepare_demo_benchmark.py','app/infrastructure/demo_workbook_reader.py',
        'app/infrastructure/import_parser.py','app/application/import_excel_dates.py',
        'app/application/demo_workbook_normalization.py','app/application/demo_workbook_admission.py',
        'app/application/contracts/demo_workbooks.py','app/application/contracts/forecast_benchmark.py',
        'app/application/forecast_benchmark_admission.py','app/domain/forecasting/stockout.py')
    code={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in source_files}
    inventory=tuple(b.metadata for b in books)
    identity=challenger_digest('demo-admission',dict(inventory=inventory,config=declarations,source=code,
                                                  protocol_digest=protocol_digest(protocol)))
    storage=BenchmarkStorage(root/'runtime/challenger/dataset-admission')
    directory=storage.path('datasets',identity)
    # Check every alias too. Filename suffixes never determine the selected content.
    for book in books:
        for path in (book.path,*(Path(p) for p in book.metadata['aliases'])):
            if hashlib.sha256(path.read_bytes()).hexdigest()!=book.sha256:
                raise ValueError('RAW_HASH_CHANGED')
    manifest.update(admission_identity=identity,protocol_digest=protocol_digest(protocol),source_revision=normalized.source_revision,
        source_code_sha256=code,raw_hashes_unchanged=True,harness_dataset_written=dataset is not None,
        execution_authorized=False,planning_input_written=False,
        canonical_dataset_meaning='Detached normalized staging; missing timezone/vintages are unresolved. No canonical DB writes.',
        declarations=declarations)
    storage.retain(directory,'sources.json',inventory)
    storage.retain(directory,'selection.json',dict(schema_version=2,source_revision=normalized.source_revision,
        inventory=str(inventory_path/'inventory.json'),selected=inventory,
        reason='One distinct content hash per recognized role in explicit uploads directory; no suffix/mtime selection.',
        exclusions='No next-week POS is present; unknown roles remain inventoried, never implicitly merged.'))
    storage.retain(directory,'normalized.json',normalized)
    storage.retain(directory,'operational-evidence.json',tables)
    storage.retain(directory,'config.json',declarations)
    storage.retain(directory,'admission.json',manifest)
    if dataset is not None:
        storage.retain(directory,'dataset.json',dataset)
        storage.retain(directory,'plan.json',plan)
    return manifest,directory


def protocol_digest(protocol):
    from scripts.forecast_benchmark_protocol import canonical_digest
    return canonical_digest(protocol)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--uploads',type=Path,required=True)
    parser.add_argument('--declarations',type=Path)
    parser.add_argument('--inventory-only',action='store_true')
    args=parser.parse_args(argv)
    try:
        if args.inventory_only:
            directory,rows=inventory_runtime(ROOT/'runtime',ROOT)
            print(canonical_bytes(dict(files=len(rows),inventory=str(directory/'inventory.json'))).decode())
            return 0
        declarations=AdmissionDeclarations() if args.declarations is None else AdmissionDeclarations.model_validate_json(args.declarations.read_bytes())
        manifest,directory=prepare(args.uploads,ROOT,declarations)
        print(canonical_bytes({k:manifest[k] for k in ('admission_identity','normalization','forecast_AB','forecast_C','paired_ABC','E4',
            'real_unseen','raw_hashes_unchanged','harness_dataset_written','execution_authorized','planned_workload')}|
            {'manifest':str(directory/'admission.json')}).decode())
        return 0
    except Exception as error:
        print(json.dumps(dict(status='BLOCKED',code=type(error).__name__,detail=str(error) if type(error) is ValueError else 'SOURCE_OR_ADMISSION_FAILURE')))
        return 2


if __name__=='__main__':raise SystemExit(main())
