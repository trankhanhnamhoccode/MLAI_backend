"""Caller holds the authenticated User fence and owns commit/rollback."""
from app.models import Store,StoreMembership
from app.models.store_creation import StoreCreationReceipt


class StoreCreationRepository:
    def __init__(self,session):self.session=session

    def receipt(self,actor,key):
        return self.session.get(StoreCreationReceipt,(actor,key))

    def create(self,user_id,store_id,membership_id,request,now):
        store=Store(id=store_id,name=request.name,timezone=request.timezone,currency=request.currency,
                    active=True,created_at=now,updated_at=now)
        self.session.add(store);self.session.flush()
        member=StoreMembership(id=membership_id,store_id=store_id,user_id=user_id,role='OWNER',
                               active=True,authorization_revision=1,created_at=now,updated_at=now)
        self.session.add(member);self.session.flush()
        return store,member
