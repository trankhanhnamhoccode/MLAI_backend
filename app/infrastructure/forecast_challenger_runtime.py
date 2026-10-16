"""Installed, non-editable forecast snapshot and exact runtime admission."""
import hashlib
import importlib.metadata as metadata
import importlib.util
import json
from pathlib import Path
import platform
import sys

from app.application.contracts.forecast_challenger import (
    ChallengerError, ChallengerFailure as Failure, DependencyPin, ENGINE_DISTRIBUTION,
    ENGINE_SOURCE_DIGEST, ENGINE_VERSION, RuntimeIdentity,
)
from app.application.forecast_challenger_validation import require

RUNTIME_PINS = {
    'lightgbm': '4.6.0', 'numpy': '2.2.6', 'scipy': '1.17.1', 'pandas': '2.2.3',
    'pydantic': '2.13.5', 'pydantic-core': '2.46.5', 'tzdata': '2026.5',
    'python-dateutil': '2.9.0.post0', 'pytz': '2026.5', 'six': '1.17.0',
    'annotated-types': '0.8.0', 'typing-extensions': '4.16.0', 'typing-inspection': '0.4.4',
}


def current_runtime() -> RuntimeIdentity:
    try:
        require(metadata.version(ENGINE_DISTRIBUTION) == ENGINE_VERSION,
                'ENGINE_VERSION_MISMATCH', Failure.DEPENDENCY_MISMATCH)
        distribution = metadata.distribution(ENGINE_DISTRIBUTION)
        root = Path(distribution.locate_file('shelfcash_forecast')).resolve()
        manifest = json.loads((root / 'snapshot_provenance.json').read_bytes())
        declared = manifest.pop('source_digest')
        actual = hashlib.sha256(json.dumps(manifest, sort_keys=True,
            separators=(',', ':')).encode()).hexdigest()
        require(actual == declared == ENGINE_SOURCE_DIGEST, 'ENGINE_SOURCE_MISMATCH',
                Failure.DEPENDENCY_MISMATCH)
        for file in manifest['files']:
            p = root.parent / file['path']
            require(not p.is_symlink() and p.resolve().is_relative_to(root) and
                    hashlib.sha256(p.read_bytes()).hexdigest() == file['sha256'],
                    'ENGINE_SOURCE_MISMATCH', Failure.DEPENDENCY_MISMATCH)
        declared_paths = {f['path'] for f in manifest['files']}
        actual_paths = {p.relative_to(root.parent).as_posix() for p in root.rglob('*.py')}
        require(actual_paths == declared_paths, 'ENGINE_SOURCE_FILE_SET', Failure.DEPENDENCY_MISMATCH)
        spec = importlib.util.find_spec('shelfcash_forecast')
        require(spec is not None and Path(spec.origin).resolve() == root / '__init__.py',
                'ENGINE_IMPORT_SHADOWED', Failure.DEPENDENCY_MISMATCH)
        for name, module in tuple(sys.modules.items()):
            if name.startswith('shelfcash_forecast.') and getattr(module, '__file__', None):
                require(Path(module.__file__).resolve().is_relative_to(root),
                        'ENGINE_IMPORT_SHADOWED', Failure.DEPENDENCY_MISMATCH)
        pins = tuple(DependencyPin(name=name, version=metadata.version(name))
                     for name in sorted(RUNTIME_PINS))
        require(all(p.version == RUNTIME_PINS[p.name] for p in pins),
                'DEPENDENCY_VERSION_MISMATCH', Failure.DEPENDENCY_MISMATCH)
        # Content identity for adapter + shared boundaries used in admission/replay.
        from app.application.forecast_challenger_serialization import challenger_digest
        base = Path(__file__).resolve().parents[1]
        files = [p for p in base.rglob('*forecast_challenger*.py') if p.is_file()]
        files += [base / 'application/contracts/common.py',
                  base / 'application/contracts/forecast_execution.py',
                  base / 'domain/forecasting/validation.py']
        code = [(p.relative_to(base).as_posix(), hashlib.sha256(p.read_bytes()).hexdigest())
                for p in sorted(files)]
        return RuntimeIdentity(adapter_code_digest=challenger_digest('code', code),
            python=platform.python_version(), platform=platform.system(), machine=platform.machine(),
            dependencies=pins)
    except ChallengerError:
        raise
    except (metadata.PackageNotFoundError, OSError, ValueError, KeyError, TypeError) as error:
        raise ChallengerError(Failure.DEPENDENCY_MISMATCH, 'CHALLENGER_RUNTIME_UNAVAILABLE') from error
