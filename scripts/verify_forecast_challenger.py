"""Tiny explicit correctness setup + native inference + fresh-process replay; no DB."""
from pathlib import Path
import subprocess
import sys

from app.application.forecast_challenger_serialization import canonical_bytes
from app.application.use_cases.forecast_challenger import ForecastChallenger
from app.infrastructure.storage.forecast_challenger import ChallengerStorage
from tests.fixtures.forecast_engine.native_setup import create_native_fixture


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    storage = root / 'runtime/challenger'
    value = create_native_fixture(storage)
    service = ForecastChallenger(ChallengerStorage(storage), enabled=True)
    result = service.execute(value)
    assert len(result.evidence.output.forecast.predictions) == 14
    assert service.execute(value).reused
    identity = result.evidence.cache_identity
    # Request convenience output outside immutable evidence directory.
    request_file = storage / f'input-{identity}.json'
    request_file.write_bytes(canonical_bytes(value))
    subprocess.run([sys.executable, '-m', 'scripts.forecast_challenger', '--enable',
                    'replay', '--identity', identity], cwd=root, check=True)
    print('Native fixed inference + cache + fresh-process exact replay: VERIFIED')
    print('Synthetic constant boosters/offsets only; no accuracy or promotion evidence.')
    print(f'input={request_file.relative_to(root).as_posix()}')


if __name__ == '__main__':
    main()
