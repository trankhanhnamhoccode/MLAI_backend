"""Trusted-generated, content-addressed LightGBM text artifacts; no upload/pickle loader."""
from dataclasses import dataclass
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
import re
import shutil
import tempfile

import lightgbm as lgb
from pydantic import ValidationError

from app.application.contracts.forecast_model import ArtifactManifest, EvaluationReport, ModelFile
from app.application.forecast_serialization import serialize_prepared
from app.infrastructure.forecast_model import QuantileModel, require_dependencies, ModelBoundaryError

PREFIX = b'shelfcash.forecast-artifact.v1\n'


class ArtifactError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class ArtifactMissingError(ArtifactError):
    pass


@dataclass(frozen=True)
class LoadedArtifact:
    identity: str
    manifest: ArtifactManifest
    model: QuantileModel


def _manifest_bytes(manifest: ArtifactManifest) -> bytes:
    payload = manifest.model_dump(mode='json')
    # Reuse exact numeric-equivalent input serialization rather than float JSON.
    payload['training_input'] = json.loads(serialize_prepared(manifest.training_input).canonical_json)
    return json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode('utf8')


def _identity(data: bytes) -> str:
    return hashlib.sha256(PREFIX+data).hexdigest()


class ForecastArtifactStore:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()

    def load(self, identity: str) -> LoadedArtifact:
        if not re.fullmatch('[0-9a-f]{64}', identity):
            raise ArtifactError('INVALID_ARTIFACT_IDENTITY')
        directory = self.root / identity
        if directory.is_symlink() or directory.resolve().parent != self.root:
            raise ArtifactError('UNSAFE_ARTIFACT_PATH')
        if not directory.exists():
            raise ArtifactMissingError('ARTIFACT_MISSING')
        try:
            if not directory.is_dir() or {p.name for p in directory.iterdir()} != {
                    'manifest.json','p25.txt','p50.txt','p75.txt'}:
                raise ArtifactError('ARTIFACT_CONTENT_MISMATCH')
            if any(p.is_symlink() for p in directory.iterdir()):
                raise ArtifactError('UNSAFE_ARTIFACT_PATH')
            data = (directory/'manifest.json').read_bytes()
            if not hmac.compare_digest(_identity(data),identity):
                raise ArtifactError('ARTIFACT_MANIFEST_DIGEST_MISMATCH')
            manifest = ArtifactManifest.model_validate_json(data)
            if data != _manifest_bytes(manifest):
                raise ArtifactError('NONCANONICAL_ARTIFACT_MANIFEST')
            if serialize_prepared(manifest.training_input).digest != manifest.training_fingerprint:
                raise ArtifactError('ARTIFACT_TRAINING_DIGEST_MISMATCH')
            model_bytes = tuple((directory/f.name).read_bytes() for f in manifest.files)
            for file,content in zip(manifest.files,model_bytes):
                if not hmac.compare_digest(hashlib.sha256(content).hexdigest(),file.digest):
                    raise ArtifactError('ARTIFACT_MODEL_DIGEST_MISMATCH')
            require_dependencies()
            boosters = tuple(lgb.Booster(model_str=content.decode('utf8')) for content in model_bytes)
            for booster,content,q in zip(boosters,model_bytes,('0.25','0.5','0.75')):
                if tuple(booster.feature_name()) != manifest.feature_names:
                    raise ArtifactError('ARTIFACT_MODEL_FEATURE_MISMATCH')
                # The trusted text also records objective/alpha; hashes protect the bytes.
                dump = booster.dump_model()
                if dump['objective'] != 'quantile':
                    raise ArtifactError('ARTIFACT_MODEL_OBJECTIVE_MISMATCH')
                # Native text parameter section, not exception-message matching.
                parameters = dict(line[1:-1].split(': ',1) for line in content.decode('utf8').splitlines()
                                  if line.startswith('[') and line.endswith(']') and ': ' in line)
                if parameters.get('alpha') != q or parameters.get('seed') != '1729':
                    raise ArtifactError('ARTIFACT_MODEL_PARAMETER_MISMATCH')
            return LoadedArtifact(identity, manifest, QuantileModel(manifest.training_input,boosters))
        except (OSError, UnicodeError, ValidationError, json.JSONDecodeError, lgb.basic.LightGBMError,
                ModelBoundaryError) as error:
            raise ArtifactError('ARTIFACT_INVALID_OR_INCOMPATIBLE') from error

    def publish(self, model: QuantileModel, evaluation: EvaluationReport) -> str:
        require_dependencies()
        encoded = serialize_prepared(model.prepared)
        if evaluation.input_fingerprint != encoded.digest:
            raise ArtifactError('ARTIFACT_EVALUATION_INPUT_MISMATCH')
        contents = tuple(b.model_to_string().encode('utf8') for b in model.boosters)
        if len(contents) != 3:
            raise ArtifactError('ARTIFACT_MODEL_COUNT')
        manifest = ArtifactManifest(training_input=model.prepared, training_fingerprint=encoded.digest,
            evaluation=evaluation, files=[ModelFile(name=name,digest=hashlib.sha256(content).hexdigest())
                for name,content in zip(('p25.txt','p50.txt','p75.txt'), contents)])
        data = _manifest_bytes(manifest)
        identity = _identity(data)
        temporary = None
        primary = None
        try:
            self.root.mkdir(parents=True,exist_ok=True)
            if (self.root/identity).exists():
                self.load(identity)  # Never overwrite; existing content must verify.
                return identity
            temporary = Path(tempfile.mkdtemp(prefix='.pending-',dir=self.root))
            for name,content in [('manifest.json',data), *zip(('p25.txt','p50.txt','p75.txt'),contents)]:
                with (temporary/name).open('xb') as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
            try:
                os.rename(temporary,self.root/identity)
            except OSError:
                if not (self.root/identity).exists():
                    raise
                self.load(identity)  # Concurrent identical publisher, not overwrite.
            self.load(identity)
            return identity
        except OSError as error:
            primary = ArtifactError('ARTIFACT_PUBLICATION_FAILED')
            raise primary from error
        except BaseException as error:
            primary = error
            raise
        finally:
            if temporary is not None and temporary.exists():
                # Only our verified private staging directory; preserve primary on cleanup failure.
                try:
                    if temporary.resolve().parent != self.root or not temporary.name.startswith('.pending-'):
                        raise ArtifactError('UNSAFE_ARTIFACT_CLEANUP')
                    shutil.rmtree(temporary)
                except Exception as cleanup:
                    logging.getLogger(__name__).exception('Artifact staging cleanup failed')
                    if primary is not None:
                        primary.add_note(f'Artifact cleanup failed: {type(cleanup).__name__}')
                    else:
                        raise ArtifactError('ARTIFACT_CLEANUP_FAILED') from cleanup
