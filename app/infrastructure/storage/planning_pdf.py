"""Private local PDF publication. Paths only derive from owned UUIDs."""
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID,uuid4
import hashlib,os

MAX_PDF_BYTES=25*1024*1024


class PDFArtifactError(Exception):
    pass


@dataclass(frozen=True)
class PreparedPDF:
    path: Path
    sha256: str
    byte_count: int


class PlanningPDFStore:
    def __init__(self,root):
        self.root=Path(root).resolve()

    def _path(self,name):
        if self.root.is_symlink():raise PDFArtifactError('Unsafe artifact root')
        path=self.root/name
        if path.is_symlink() or path.resolve().parent!=self.root:raise PDFArtifactError('Unsafe artifact path')
        return path

    def prepare(self,export_id,data):
        UUID(str(export_id))
        if not data.startswith(b'%PDF-') or not 0<len(data)<=MAX_PDF_BYTES:raise PDFArtifactError('Invalid/oversized PDF')
        self.root.mkdir(parents=True,exist_ok=True)
        path=self._path(f'{export_id}.{uuid4()}.tmp')
        with path.open('xb') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        try:path.chmod(0o600)
        except OSError:
            path.unlink();raise
        return PreparedPDF(path,hashlib.sha256(data).hexdigest(),len(data))

    def publish(self,export_id,prepared):
        path=self._path(prepared.path.name)
        target=self._path(str(UUID(str(export_id)))+'.pdf')
        if target.exists():
            self.read(export_id,prepared.sha256,prepared.byte_count)
            path.unlink()
        else:os.replace(path,target)
        # Directory fsync is supported on POSIX; Windows uses atomic replacement
        # of the fsynced file. DB success still requires final bytes/hash proof.
        if os.name!='nt':
            descriptor=os.open(self.root,os.O_RDONLY)
            try:os.fsync(descriptor)
            finally:os.close(descriptor)
        self.read(export_id,prepared.sha256,prepared.byte_count)

    def read(self,export_id,sha256,byte_count):
        try:
            path=self._path(str(UUID(str(export_id)))+'.pdf')
            if not 0<byte_count<=MAX_PDF_BYTES or path.stat().st_size!=byte_count:raise PDFArtifactError('Artifact size mismatch')
            data=path.read_bytes()
            if not data.startswith(b'%PDF-') or hashlib.sha256(data).hexdigest()!=sha256:raise PDFArtifactError('Artifact digest mismatch')
            return data
        except (OSError,ValueError) as error:raise PDFArtifactError('Artifact unavailable') from error

    def discard(self,prepared):
        path=self._path(prepared.path.name)
        path.unlink(missing_ok=True)

    def availability(self,export_id,sha256,byte_count):
        """Read proof only; distinguish absent bytes from unverifiable artifacts."""
        try:
            path=self._path(str(UUID(str(export_id)))+'.pdf')
            if not path.exists():return 'missing'
            self.read(export_id,sha256,byte_count)
            return 'available'
        except (PDFArtifactError,OSError,ValueError):return 'unverifiable'
