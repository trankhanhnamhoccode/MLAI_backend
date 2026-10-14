"""Current-authority read-only operational discovery, without engine calls."""
import unicodedata
from app.application.contracts.auth import AuthError
from app.application.contracts import discovery as dto
from app.application.import_identity import content_digest
from app.application.use_cases.collaboration_paging import page
from app.infrastructure.database.auth_session import auth_session
from app.repositories.discovery import supplier_identities


def folded(value: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', value.casefold().replace('đ','d'))
                   if not unicodedata.combining(c))


class DiscoveryReads:
    def __init__(self, auth):
        self.auth, self.engine = auth, auth.engine

    def suppliers(self, token, store, request_id, q=None, active=None, sort='name',
                  limit=50, cursor=None, snapshot_id=None):
        if q is not None:
            q = q.strip()
            if not 1 <= len(q) <= 200: raise AuthError('INVALID_FILTER',422)
        if sort not in ('name','-name'): raise AuthError('INVALID_FILTER',422)
        with self.engine.connect().execution_options(isolation_level='REPEATABLE READ') as connection:
            with auth_session(connection) as s:
                actor, authority, _ = self.auth.authorize_in_session(s,token,store,('supplier.read',))
                rows = [r for r in supplier_identities(s,store)
                        if (active is None or r['active'] == active) and (q is None or folded(q) in folded(r['name']))]
                rows.sort(key=lambda r:str(r['id']))
                rows.sort(key=lambda r:folded(r['name']),reverse=sort=='-name')
                items = tuple(dto.SupplierPickerItem(supplier_id=r['id'], name=r['name'],active=r['active'],
                    version=content_digest({k:str(v) for k,v in r.items()})) for r in rows)
                auth_binding=[str(actor.user_id),str(store),authority.authorization_version]
                filters=dict(q=q,active=active,sort=sort)
                selected, meta=page(self.auth,token,'supplier-picker',items,auth_binding,filters,limit,cursor,
                    fingerprint_facts=[auth_binding,filters])
                if snapshot_id is not None and snapshot_id != meta['snapshot_id']:
                    raise AuthError('SNAPSHOT_NOT_AVAILABLE',409)
                s.commit()
                return dto.SupplierPickerEnvelope(data=dto.SupplierPicker(items=selected),
                    meta=dto.DiscoveryMeta(request_id=request_id,**meta),error=None)
