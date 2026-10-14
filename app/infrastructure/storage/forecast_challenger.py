"""Private immutable local artifacts/evidence, separate from host operational storage."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import tempfile

from pydantic import ValidationError

from app.application.contracts.forecast_challenger import (
    ChallengerArtifact, ChallengerError, ChallengerEvidence, ChallengerFailure as Failure,
)
from app.application.forecast_challenger_serialization import canonical_bytes, challenger_digest
from app.application.forecast_challenger_validation import require

CORE_FILES = frozenset({
    'model_q25.txt', 'model_q50.txt', 'model_q75.txt', 'feature_schema.json',
    'preprocessing_config.json', 'category_mappings.json', 'model_metadata.json',
    'point_corrector.json', 'calibrator.json', 'training_manifest.json',
    'artifact_checksums.json',
})


@dataclass(frozen=True)
class AdmittedArtifactBytes:
    manifest: ChallengerArtifact
    directory: Path


class ChallengerStorage:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def _path(self, kind: str, identity: str) -> Path:
        require(re.fullmatch('[0-9a-f]{64}', identity) is not None, 'INVALID_STORAGE_IDENTITY')
        parent = self.root / kind
        path = parent / identity
        require(not parent.is_symlink() and not path.is_symlink() and
                path.resolve().parent == parent.resolve() and
                parent.resolve().parent == self.root, 'UNSAFE_STORAGE_PATH', Failure.ARTIFACT_CORRUPTION)
        return path

    def load_artifact(self, identity: str) -> AdmittedArtifactBytes:
        directory = self._path('artifacts', identity)
        require(directory.is_dir(), 'PINNED_ARTIFACT_MISSING', Failure.TECHNICAL_FAILURE)
        try:
            raw = (directory / 'adapter_manifest.json').read_bytes()
            manifest = ChallengerArtifact.model_validate_json(raw)
            require(challenger_digest('artifact', manifest) == identity and raw == canonical_bytes(manifest),
                    'ARTIFACT_MANIFEST_DIGEST_MISMATCH', Failure.ARTIFACT_CORRUPTION)
            require(set(p.name for p in directory.iterdir()) == CORE_FILES | {'adapter_manifest.json'} and
                    {f.name for f in manifest.files} == CORE_FILES and len(manifest.files) == len(CORE_FILES),
                    'ARTIFACT_FILE_SET', Failure.ARTIFACT_CORRUPTION)
            for file in manifest.files:
                p = directory / file.name
                require(not p.is_symlink() and p.is_file() and p.resolve().parent == directory,
                        'UNSAFE_ARTIFACT_FILE', Failure.ARTIFACT_CORRUPTION)
                require(hashlib.sha256(p.read_bytes()).hexdigest() == file.digest,
                        'ARTIFACT_CHECKSUM_MISMATCH', Failure.ARTIFACT_CORRUPTION)
            checksums = json.loads((directory / 'artifact_checksums.json').read_bytes())
            expected = {f.name: f.digest for f in manifest.files if f.name != 'artifact_checksums.json'}
            require(checksums == {'algorithm': 'sha256', 'files': expected},
                    'ARTIFACT_CHECKSUM_COVERAGE', Failure.ARTIFACT_CORRUPTION)
            return AdmittedArtifactBytes(manifest, directory)
        except ChallengerError:
            raise
        except (OSError, ValueError, ValidationError, KeyError) as error:
            raise ChallengerError(Failure.ARTIFACT_CORRUPTION, 'INVALID_PINNED_ARTIFACT') from error

    def publish_artifact(self, manifest: ChallengerArtifact, files: dict[str, bytes]) -> str:
        """Explicit trusted setup/import only; never called by inference or replay."""
        require(set(files) == CORE_FILES and {f.name for f in manifest.files} == CORE_FILES,
                'ARTIFACT_FILE_SET', Failure.ARTIFACT_CORRUPTION)
        require(len(manifest.files) == len(CORE_FILES) and all(
            hashlib.sha256(files[f.name]).hexdigest() == f.digest for f in manifest.files),
            'ARTIFACT_CHECKSUM_MISMATCH', Failure.ARTIFACT_CORRUPTION)
        identity = challenger_digest('artifact', manifest)
        content = dict(files, adapter_manifest_json=canonical_bytes(manifest))
        content['adapter_manifest.json'] = content.pop('adapter_manifest_json')
        self._publish('artifacts', identity, content)
        self.load_artifact(identity)
        return identity

    def load_evidence(self, identity: str) -> ChallengerEvidence | None:
        directory = self._path('runs', identity)
        if not directory.exists():
            return None
        try:
            require(set(p.name for p in directory.iterdir()) == {'evidence.json', 'evidence.sha256'},
                    'EVIDENCE_FILE_SET', Failure.ARTIFACT_CORRUPTION)
            require(not any(p.is_symlink() for p in directory.iterdir()),
                    'UNSAFE_EVIDENCE_FILE', Failure.ARTIFACT_CORRUPTION)
            raw = (directory / 'evidence.json').read_bytes()
            expected = (directory / 'evidence.sha256').read_text(encoding='ascii')
            require(hashlib.sha256(raw).hexdigest() == expected,
                    'EVIDENCE_DIGEST_MISMATCH', Failure.ARTIFACT_CORRUPTION)
            evidence = ChallengerEvidence.model_validate_json(raw)
            require(raw == canonical_bytes(evidence) and evidence.cache_identity == identity,
                    'EVIDENCE_IDENTITY_MISMATCH', Failure.ARTIFACT_CORRUPTION)
            return evidence
        except ChallengerError:
            raise
        except (OSError, ValueError, ValidationError) as error:
            raise ChallengerError(Failure.ARTIFACT_CORRUPTION, 'INVALID_RETAINED_EVIDENCE') from error

    def retain(self, evidence: ChallengerEvidence) -> None:
        raw = canonical_bytes(evidence)
        self._publish('runs', evidence.cache_identity, {
            'evidence.json': raw, 'evidence.sha256': hashlib.sha256(raw).hexdigest().encode('ascii'),
        })

    def _publish(self, kind: str, identity: str, content: dict[str, bytes]) -> None:
        path = self._path(kind, identity)
        if path.exists():
            require(set(p.name for p in path.iterdir()) == set(content),
                    'IMMUTABLE_STORAGE_CONFLICT', Failure.ARTIFACT_CORRUPTION)
            require(all(not (path / name).is_symlink() and (path / name).read_bytes() == data
                        for name, data in content.items()), 'IMMUTABLE_STORAGE_CONFLICT', Failure.ARTIFACT_CORRUPTION)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        # Pending directories are retained on failure for inspection, never purge runtime.
        staging = Path(tempfile.mkdtemp(prefix='.pending-', dir=path.parent))
        try:
            for name, data in content.items():
                with (staging / name).open('xb') as stream:
                    stream.write(data)
                    stream.flush()
                    import os
                    os.fsync(stream.fileno())
            staging.rename(path)
        except OSError as error:
            # An identical concurrent publisher may have won; verify exact bytes.
            if path.exists() and set(p.name for p in path.iterdir()) == set(content) and all(
                    not (path / name).is_symlink() and (path / name).read_bytes() == data
                    for name, data in content.items()):
                return
            raise ChallengerError(Failure.TECHNICAL_FAILURE, 'LOCAL_PUBLICATION_FAILED') from error
