"""Explicit offline challenger CLI; no .env/application/DB/server startup."""
import argparse
import json
from pathlib import Path
import sys

from pydantic import ValidationError

from app.application.contracts.forecast_challenger import ChallengerError, ChallengerInput
from app.application.forecast_challenger_serialization import canonical_bytes
from app.application.use_cases.forecast_challenger import ForecastChallenger
from app.infrastructure.storage.forecast_challenger import ChallengerStorage

ROOT = Path(__file__).resolve().parents[1]
STORAGE = ROOT / 'runtime/challenger'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--enable', action='store_true', help='Required explicit opt-in; default disabled')
    sub = parser.add_subparsers(dest='command', required=True)
    execute = sub.add_parser('infer')
    execute.add_argument('--input', type=Path, required=True)
    replay = sub.add_parser('replay')
    replay.add_argument('--identity', required=True)
    args = parser.parse_args(argv)
    service = ForecastChallenger(ChallengerStorage(STORAGE), enabled=args.enable)
    try:
        if args.command == 'infer':
            value = ChallengerInput.model_validate_json(args.input.read_bytes())
            result = service.execute(value)
        else:
            result = service.replay(args.identity)
        print(json.dumps({'status': 'VERIFIED', 'cache_identity': result.evidence.cache_identity,
            'reused': result.reused, 'prediction_count': len(result.evidence.output.forecast.predictions),
            'artifact_purpose': result.evidence.output.artifact.purpose,
            'promotion': 'NOT_ENABLED'}, sort_keys=True))
        return 0
    except ChallengerError as error:
        print(json.dumps({'status': 'REJECTED', 'category': error.category.value, 'code': error.code}))
        return 2
    except (OSError, ValidationError, ValueError):
        print(json.dumps({'status': 'REJECTED', 'category': 'UNSUPPORTED', 'code': 'INVALID_INPUT_FILE'}))
        return 2


if __name__ == '__main__':
    sys.exit(main())
