"""Run only small E1 JSON/protocol checks. No model, DB, worker or network calls."""
from pathlib import Path
import json

from scripts.forecast_benchmark_protocol import (
    ProtocolError, canonical_digest, materialize_fixture, validate_case, validate_manifest,
)

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    manifest = json.loads((ROOT / 'tests/fixtures/forecast_engine/benchmark_manifest.json').read_text())
    tasks = validate_manifest(manifest)
    fixtures = json.loads((ROOT / 'tests/fixtures/forecast_engine/compatibility_cases.json').read_text())
    expected_digest = canonical_digest(fixtures['base'])
    for fixture in fixtures['cases']:
        case = materialize_fixture(fixtures['base'], fixture['changes'])
        try:
            validate_case(case)
            actual = 'VALID'
        except ProtocolError as error:
            actual = f'{error.outcome.value}:{error.code}'
        if actual != fixture['expected']:
            raise AssertionError(f"{fixture['name']}: expected {fixture['expected']}, got {actual}")
    assert expected_digest == canonical_digest(fixtures['base']), 'Fixture base mutated'
    print(f'E1 offline PASS: {len(tasks)} origins, {len(fixtures["cases"])} compatibility cases')
    print(f'protocol_sha256={canonical_digest(manifest)}')
    print('Synthetic admission examples only; no inference/accuracy/promotion evidence.')


if __name__ == '__main__':
    main()
