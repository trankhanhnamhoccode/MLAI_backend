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
from app.infrastructure.demo_workbook_reader import discover_workbooks
from app.infrastructure.forecast_benchmark_storage import BenchmarkStorage

ROOT=Path(__file__).resolve().parents[1]


def prepare(uploads:Path,root:Path,declarations:AdmissionDeclarations):
    books=discover_workbooks(uploads)
    normalized,issues=normalize_demo(books,declarations.timezone)
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
    args=parser.parse_args(argv)
    try:
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
