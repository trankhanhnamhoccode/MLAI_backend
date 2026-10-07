"""Internal trusted operator CLI, not an import/business API. No reset/migration."""
import argparse
import json
from pathlib import Path
from uuid import UUID

from app.application.contracts.common import RunReferenceInput
from app.application.contracts.forecast_execution import ForecastExecutionInput, PreparedForecastInput
from app.application.forecast_serialization import serialize_prepared
from app.application.use_cases.forecast_evaluation import backtest
from app.application.use_cases.forecast_trained_execution import TrainedForecastExecutionUseCases
from app.config import Settings
from app.infrastructure.database.engine import create_database_engine
from app.infrastructure.forecast_model import train_quantiles, predict_quantiles
from app.infrastructure.storage.forecast_artifacts import ForecastArtifactStore
from scripts.dev import inspect_database, require_head, validate_reset_target
from scripts.forecast_demo import synthetic_input


def _write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    # Refuse overwriting operator inputs/artifacts/reports accidentally.
    with path.open('x',encoding='utf8') as stream:
        stream.write(value+'\n')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('synthetic','backtest','train','infer','capture','execute','replay'))
    parser.add_argument('--input',type=Path,help='Trusted prepared JSON, or execution-request JSON for capture/execute')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--artifact-root',type=Path,default=Path('runtime/model_artifacts'))
    parser.add_argument('--artifact')
    parser.add_argument('--dataset-label',choices=('SYNTHETIC','USER_PROVIDED_UNVERIFIED'),
                        default='USER_PROVIDED_UNVERIFIED')
    parser.add_argument('--store-id',type=UUID)
    parser.add_argument('--run-id',type=UUID)
    parser.add_argument('--persist',action='store_true',help='Replay as a new run')
    parser.add_argument('--database',choices=('test','development'),default='test')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('--output already exists; choose a new file')
    if args.command == 'synthetic':
        _write(args.output,serialize_prepared(synthetic_input()).canonical_json)
        print('SYNTHETIC only; no real quality evidence')
        return
    artifacts = ForecastArtifactStore(args.artifact_root)
    if args.command in ('backtest','train','infer'):
        if args.input is None:
            parser.error('--input required')
        prepared = PreparedForecastInput.model_validate_json(args.input.read_bytes())
        if args.command == 'infer':
            if args.artifact is None:
                parser.error('--artifact required for pure inference; no implicit fallback')
            loaded = artifacts.load(args.artifact)
            result,_,_ = predict_quantiles(loaded.model,prepared,args.artifact)
            _write(args.output,result.model_dump_json(indent=2))
        else:
            report = backtest(prepared,args.dataset_label)
            if args.command == 'backtest':
                _write(args.output,report.model_dump_json(indent=2))
            else:
                identity = artifacts.publish(train_quantiles(prepared),report)
                _write(args.output,json.dumps(dict(artifact_identity=identity,
                    selected_family=report.selected_family,selection_reason=report.selection_reason,
                    real_data_quality=report.real_data_quality),indent=2))
                print(identity)
        return
    current = Settings()
    settings = Settings(_env_file=None,environment='test' if args.database=='test' else 'development',
                        database_url=current.test_database_url if args.database=='test' else current.database_url)
    if args.database == 'test':
        validate_reset_target(settings)
    require_head(inspect_database(settings))  # Read-only check; never migrate/reset.
    engine = create_database_engine(settings)
    try:
        cases = TrainedForecastExecutionUseCases(engine,artifacts)
        if args.command == 'replay':
            if args.store_id is None or args.run_id is None:
                parser.error('--store-id and --run-id required')
            reference = RunReferenceInput(store_id=args.store_id,run_id=args.run_id)
            if args.persist:
                run = cases.replay_persisted(reference)
                result = cases.get_with_metadata(RunReferenceInput(store_id=args.store_id,run_id=run.id))
            else:
                result = cases.replay(reference)
            _write(args.output,result.model_dump_json(indent=2))
        else:
            if args.input is None:
                parser.error('--input required')
            request = ForecastExecutionInput.model_validate_json(args.input.read_bytes())
            if args.command == 'capture':
                _write(args.output,serialize_prepared(cases.capture(request)).canonical_json)
            else:
                run = cases.execute(request,args.artifact)
                result = cases.get_with_metadata(RunReferenceInput(store_id=request.store_id,run_id=run.id))
                _write(args.output,result.model_dump_json(indent=2))
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
