"""Explicit opt-in fixed challenger execution/cache/replay; no operational DB."""
from dataclasses import dataclass
from pydantic import ValidationError

from app.application.contracts.forecast_challenger import (
    ChallengerError, ChallengerEvidence, ChallengerFailure as Failure, ChallengerInput,
    ChallengerOutput, RuntimeIdentity,
)
from app.application.forecast_challenger_serialization import canonical_bytes, challenger_digest
from app.application.forecast_challenger_validation import (
    admit_artifact, admit_input, require, validate_output,
)
from app.infrastructure.forecast_challenger_runtime import current_runtime
from app.infrastructure.forecast_challenger_native import infer_native
from app.infrastructure.storage.forecast_challenger import AdmittedArtifactBytes, ChallengerStorage


@dataclass(frozen=True)
class ChallengerExecution:
    evidence: ChallengerEvidence
    reused: bool


class ForecastChallenger:
    def __init__(self, storage: ChallengerStorage, *, enabled: bool = False):
        self.storage, self.enabled = storage, enabled

    def _admit(self, value: ChallengerInput) -> tuple[ChallengerInput, RuntimeIdentity, AdmittedArtifactBytes, str]:
        require(self.enabled, 'CHALLENGER_DISABLED')
        try:
            value = ChallengerInput.model_validate(value)
        except ValidationError as error:
            raise ChallengerError(Failure.UNSUPPORTED, 'INVALID_CHALLENGER_INPUT') from error
        admit_input(value)
        runtime = current_runtime()
        bundle = self.storage.load_artifact(value.artifact_identity)
        admit_artifact(value, bundle.manifest)
        require(bundle.manifest.runtime == runtime, 'ARTIFACT_RUNTIME_MISMATCH', Failure.DEPENDENCY_MISMATCH)
        from app.infrastructure.forecast_challenger_native import verify_native_manifest
        try:
            verify_native_manifest(bundle)
        except (ImportError, OSError) as error:
            raise ChallengerError(Failure.DEPENDENCY_MISMATCH, 'NATIVE_DEPENDENCY_UNAVAILABLE') from error
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, ChallengerError):
                raise
            raise ChallengerError(Failure.ARTIFACT_CORRUPTION, 'NATIVE_MANIFEST_INVALID') from error
        key = challenger_digest('cache', {'input': value, 'runtime': runtime})
        return value, runtime, bundle, key

    def _verify_retained(self, value: ChallengerInput, runtime: RuntimeIdentity,
                         bundle: AdmittedArtifactBytes, key: str, evidence: ChallengerEvidence) -> None:
        require(evidence.cache_identity == key and evidence.input == value and
                evidence.output.input_digest == challenger_digest('input', value) and
                evidence.output.runtime == runtime and evidence.output.artifact == bundle.manifest,
                'RETAINED_BINDING_MISMATCH', Failure.ARTIFACT_CORRUPTION)
        validate_output(value, evidence.output)

    @staticmethod
    def _compute(value: ChallengerInput, bundle: AdmittedArtifactBytes,
                 runtime: RuntimeIdentity) -> ChallengerOutput:
        try:
            return infer_native(value, bundle, runtime)
        except ChallengerError:
            raise
        except (ImportError, OSError) as error:
            raise ChallengerError(Failure.DEPENDENCY_MISMATCH, 'NATIVE_DEPENDENCY_UNAVAILABLE') from error
        except Exception as error:
            # Programming/unexpected native failures remain failures, never fallback success.
            raise ChallengerError(Failure.TECHNICAL_FAILURE, 'NATIVE_TECHNICAL_FAILURE') from error

    def execute(self, value: ChallengerInput) -> ChallengerExecution:
        value, runtime, bundle, key = self._admit(value)
        retained = self.storage.load_evidence(key)
        if retained is not None:
            self._verify_retained(value, runtime, bundle, key, retained)
            return ChallengerExecution(retained, True)
        output = self._compute(value, bundle, runtime)
        evidence = ChallengerEvidence(cache_identity=key, input=value, output=output)
        self.storage.retain(evidence)
        # Re-read persisted bytes; execution result alone is not retention evidence.
        stored = self.storage.load_evidence(key)
        require(stored is not None and canonical_bytes(stored) == canonical_bytes(evidence),
                'RETENTION_READBACK_FAILED', Failure.TECHNICAL_FAILURE)
        return ChallengerExecution(stored, False)

    def replay(self, identity: str) -> ChallengerExecution:
        require(self.enabled, 'CHALLENGER_DISABLED')
        retained = self.storage.load_evidence(identity)
        require(retained is not None, 'RETAINED_EVIDENCE_MISSING', Failure.TECHNICAL_FAILURE)
        value, runtime, bundle, key = self._admit(retained.input)
        require(identity == key, 'REPLAY_RUNTIME_OR_INPUT_MISMATCH', Failure.DEPENDENCY_MISMATCH)
        self._verify_retained(value, runtime, bundle, key, retained)
        actual = self._compute(value, bundle, runtime)
        require(canonical_bytes(actual) == canonical_bytes(retained.output),
                'REPLAY_OUTPUT_MISMATCH', Failure.TECHNICAL_FAILURE)
        return ChallengerExecution(retained, False)
