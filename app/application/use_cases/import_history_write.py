"""Transaction-owned append writer; retained completion is the public history reader."""
from hashlib import sha256
from sqlalchemy import select, func
from app.application.contracts.auth import AuthError
from app.application.contracts.import_history import HISTORY_MODELS
from app.models.import_history import ImportHistoryRecord


def write_history(session, store_id, row, scope, provenance, recorded_at):
    value = HISTORY_MODELS[row.after.domain].model_validate(row.after.model_dump())
    current = session.scalar(select(func.max(ImportHistoryRecord.version)).where(
        ImportHistoryRecord.store_id == store_id,
        ImportHistoryRecord.domain == value.domain,
        ImportHistoryRecord.source_system_key == scope.source_system_key,
        ImportHistoryRecord.report_type == scope.report_type,
        ImportHistoryRecord.source_record_key == value.source_record_key))
    if (str(current) if current is not None else None) != row.expected_version:
        raise AuthError('PREVIEW_STALE', 409)
    if row.proposed_action not in {'CREATE_HISTORY_RECORD', 'CORRECT_HISTORY_RECORD'}:
        raise AuthError('PREVIEW_BLOCKED', 409)
    version = (current or 0) + 1
    session.add(ImportHistoryRecord(id=row.target_reserved_or_existing_id, store_id=store_id,
        domain=value.domain, source_system_key=scope.source_system_key, report_type=scope.report_type,
        source_record_key=value.source_record_key,
        source_record_hash=sha256(value.source_record_key.encode()).hexdigest(), version=version,
        payload=value.model_dump(mode='json'), provenance=provenance, recorded_at=recorded_at))
    session.flush()
    return version
