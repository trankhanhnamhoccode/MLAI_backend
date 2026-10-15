"""Pin existing immutable source provenance and its exact Import audit when known."""
from collections.abc import Mapping,Sequence
from app.application.contracts.planning_source_evidence import SourceConfirmation
from app.application.import_identity import content_digest


def source_confirmation(entity: str,identifier: str,row: Mapping[str,object],
                        audits: Sequence[Mapping[str,object]]) -> SourceConfirmation:
    provenance=row.get('provenance',{})
    row_id=provenance.get('row',{}).get('row_id')
    matches=[]
    if row_id:
        for audit in audits:
            if audit['store_id']!=row['store_id']:continue
            refs=audit['record_json'].get('completion',{}).get('canonical_references',())
            if any(ref['canonical_id']==identifier and ref['row_id']==row_id for ref in refs):
                matches.append(audit)
    proof=matches[0] if len(matches)==1 else None
    return SourceConfirmation(entity=entity,entity_id=identifier,provenance_digest=content_digest(provenance),
        source_system_key=row['source_system_key'],source_record_key=row['source_record_key'],
        actor_id=proof['actor_id'] if proof else None,confirmed_at=proof['occurred_at'] if proof else None,
        audit_id=proof['id'] if proof else None)
