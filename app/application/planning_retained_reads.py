"""Process-owned terminal reads, bounded by entry count and canonical byte size.

Every lookup hashes the complete stored aggregate and binds all persistence
identity columns. Cold reads still perform the full semantic/canonical decoder.
Authorization belongs to the caller and is required on every request.
"""
from collections import OrderedDict
from threading import RLock
from app.application.planning_serialization import canonical_bytes,digest
from app.application.planning_public_projection import project_run
from app.application.use_cases.planning_run import decode_row
from app.application.contracts.planning_run import PlanningPersistenceError


class VerifiedPlanningReads:
    def __init__(self, *, max_entries=4, max_canonical_bytes=16*1024*1024):
        if max_entries<1 or max_canonical_bytes<1:raise ValueError('Cache bounds must be positive')
        self.max_entries,self.max_canonical_bytes=max_entries,max_canonical_bytes
        self._entries=OrderedDict()
        self._bytes=0
        self._lock=RLock()

    def read(self,row, *, require_cached=False, evidence=False):
        if row is None:raise PlanningPersistenceError('NOT_FOUND')
        try:
            size=len(canonical_bytes(row.record_json))
            actual=digest('aggregate',row.record_json)
            if actual!=row.record_digest:raise ValueError('Aggregate digest mismatch')
            key=(evidence,actual,row.revision,row.id,row.actor_id,row.store_id,row.operation,
                 row.key_digest,row.request_digest,row.status,row.accepted_at)
        except (ValueError,TypeError) as error:
            raise PlanningPersistenceError('RESULT_INTEGRITY_UNAVAILABLE',row.id) from error
        with self._lock:
            if key in self._entries:
                self._entries.move_to_end(key)
                return self._entries[key][1:]
            # Assistant L1 accepts only a previously verified aggregate. The
            # existing cold semantic decoder re-evaluates exact business facts;
            # do not silently run that work on the wording/evidence path.
            if require_cached:
                raise PlanningPersistenceError('EVIDENCE_NOT_VERIFIED', row.id)
            record=decode_row(row,retained_consistency=True) if evidence else decode_row(row)
            view=project_run(record,response_version=actual)
            if record.status in ('completed','failed') and size<=self.max_canonical_bytes:
                while self._entries and (len(self._entries)>=self.max_entries or self._bytes+size>self.max_canonical_bytes):
                    _,entry=self._entries.popitem(last=False)
                    self._bytes-=entry[0]
                self._entries[key]=(size,record,view)
                self._bytes+=size
            return record,view
