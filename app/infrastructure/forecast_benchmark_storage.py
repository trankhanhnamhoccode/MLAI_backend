"""Concrete private E3 checkpoints; frozen inputs and content digests, no cleanup."""
import hashlib
import json
from pathlib import Path
import tempfile
from time import monotonic

from app.application.contracts.forecast_benchmark import BenchmarkBudget
from app.application.contracts.forecast_challenger import ChallengerError, ChallengerFailure as Failure
from app.application.forecast_challenger_serialization import canonical_bytes, challenger_digest
from app.application.forecast_challenger_validation import require


class BudgetExceeded(RuntimeError):
    pass


class FitBudget:
    def __init__(self, budget: BenchmarkBudget, *, spent_seconds=0, boosters=0, postprocess=0):
        self.budget, self.boosters, self.postprocess = budget, boosters, postprocess
        self.started = monotonic()
        self.spent_seconds = float(spent_seconds)

    def check(self):
        if monotonic()-self.started+self.spent_seconds >= self.budget.wall_seconds:
            raise BudgetExceeded('WALL_BUDGET_EXCEEDED')

    def booster(self):
        self.check()
        if self.boosters >= self.budget.maximum_booster_fits:
            raise BudgetExceeded('BOOSTER_FIT_BUDGET_EXCEEDED')
        self.boosters += 1

    def calibration(self):
        self.check()
        if self.postprocess >= self.budget.maximum_postprocess_fits:
            raise BudgetExceeded('POSTPROCESS_FIT_BUDGET_EXCEEDED')
        self.postprocess += 1

    def callback(self, environment):
        self.check()


def training_source_identity() -> str:
    root = Path(__file__).resolve().parents[1]
    paths = ['infrastructure/forecast_benchmark_features.py', 'infrastructure/forecast_benchmark_training.py',
             'application/contracts/forecast_benchmark.py', 'application/forecast_benchmark_admission.py']
    return challenger_digest('training-source', [(p,hashlib.sha256((root/p).read_bytes()).hexdigest()) for p in paths])


class BenchmarkStorage:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def path(self, category: str, identity: str):
        require(len(identity)==64 and all(c in '0123456789abcdef' for c in identity), 'INVALID_BENCHMARK_KEY')
        path = self.root/category/identity
        require(not path.is_symlink() and path.resolve().is_relative_to(self.root) and
                not path.parent.is_symlink(), 'UNSAFE_BENCHMARK_PATH', Failure.ARTIFACT_CORRUPTION)
        return path

    def retain(self, directory: Path, name: str, value) -> None:
        raw = canonical_bytes(value)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory/name
        if path.exists():
            require(canonical_bytes(self.load(directory,name))==raw,
                    'IMMUTABLE_BENCHMARK_CONFLICT', Failure.ARTIFACT_CORRUPTION)
            return
        # Hash and payload in one immutable envelope; no two-file half-publication.
        envelope = canonical_bytes({'sha256':hashlib.sha256(raw).hexdigest(), 'value':json.loads(raw)})
        with tempfile.NamedTemporaryFile(prefix='.pending-', dir=directory, delete=False) as file:
            file.write(envelope)
            file.flush()
            import os
            os.fsync(file.fileno())
            temporary = Path(file.name)
        try:
            temporary.rename(path)
        except OSError as error:
            if not path.exists() or path.read_bytes()!=envelope:
                raise ChallengerError(Failure.TECHNICAL_FAILURE,'BENCHMARK_PUBLICATION_FAILED') from error

    def load(self, directory: Path, name: str):
        path=directory/name
        if not path.exists():
            return None
        try:
            require(not path.is_symlink(), 'UNSAFE_BENCHMARK_PATH', Failure.ARTIFACT_CORRUPTION)
            envelope=json.loads(path.read_bytes())
            raw=canonical_bytes(envelope['value'])
            require(hashlib.sha256(raw).hexdigest()==envelope['sha256'],
                    'BENCHMARK_DIGEST_MISMATCH', Failure.ARTIFACT_CORRUPTION)
            return envelope['value']
        except (OSError, ValueError, KeyError, TypeError) as error:
            if isinstance(error, ChallengerError):
                raise
            raise ChallengerError(Failure.ARTIFACT_CORRUPTION,'BENCHMARK_CHECKPOINT_INVALID') from error
