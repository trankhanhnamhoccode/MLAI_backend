"""Self-service onboarding; no operator proof, fixture or implicit business facts."""
from uuid import uuid4
from app.application.contracts.auth import AuthError,StoreSummary
from app.application.contracts.store_creation import StoreCreateRequest
from app.infrastructure.auth_crypto import digest
from app.infrastructure.database.auth_session import auth_session
from app.models.auth import AuthAudit
from app.models.store_creation import StoreCreationReceipt
from app.repositories.store_creation import StoreCreationRepository


class StoreCreation:
    def __init__(self,auth):self.auth=auth

    def _record(self,session,user,store,key,request_digest,result,request_id,now):
        session.add(StoreCreationReceipt(actor_id=user.id,key_digest=key,request_digest=request_digest,
            store_id=store.id,result=result.model_dump(mode='json'),created_at=now))
        session.add(AuthAudit(id=uuid4(),kind='STORE_CREATED',user_id=user.id,store_id=store.id,
            request_reference='store-create:'+str(uuid4()),request_digest=request_digest,
            evidence_reference='authenticated holder self-service; request='+request_id,occurred_at=now))

    def create(self,token,csrf,key,request,request_id):
        request=StoreCreateRequest.model_validate(request.model_dump())
        if not key:raise AuthError('PRECONDITION_REQUIRED',428)
        if not 1<=len(key)<=128 or not key.strip() or not key.isascii() or any(ord(c)<33 or ord(c)>126 for c in key):
            raise AuthError('INVALID_IDEMPOTENCY_KEY',422)
        fingerprint=digest(request.model_dump_json());key_digest=digest(key)
        with auth_session(self.auth.engine) as session:
            user,_=self.auth._resolve(session,token,csrf or '')
            repo=StoreCreationRepository(session)
            previous=repo.receipt(user.id,key_digest)
            if previous:
                self.auth.authorize_in_session(session,token,previous.store_id,owner_only=True,csrf=csrf or '')
                if previous.request_digest!=fingerprint:raise AuthError('IDEMPOTENCY_CONFLICT',409)
                result=StoreSummary.model_validate(previous.result)
            else:
                now=self.auth.clock()
                store,member=repo.create(user.id,uuid4(),uuid4(),request,now)
                result,_=self.auth._summary(session,store,member)
                self._record(session,user,store,key_digest,fingerprint,result,request_id,now)
            session.commit()
        return result
