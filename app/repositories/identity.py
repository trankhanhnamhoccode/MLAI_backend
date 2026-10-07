"""Global identity/bootstrap and explicitly scoped membership persistence."""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Store, StoreMembership, User
from app.repositories._guards import require_new, require_store


class IdentityRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_user(self, user: User) -> None:
        require_new(user)
        self._session.add(user)

    def get_user_by_id(self, user_id: UUID) -> User | None:
        return self._session.scalar(select(User).where(User.id == user_id))

    def get_user_by_email(self, email: str) -> User | None:
        return self._session.scalar(select(User).where(User.email == email))

    def add_membership(self, store_id: UUID, membership: StoreMembership) -> None:
        require_store(store_id, membership.store_id)
        require_new(membership)
        self._session.add(membership)

    def get_membership_by_id(self, store_id: UUID, membership_id: UUID) -> StoreMembership | None:
        return self._session.scalar(select(StoreMembership).where(StoreMembership.store_id == store_id, StoreMembership.id == membership_id))

    def get_membership(self, store_id: UUID, user_id: UUID) -> StoreMembership | None:
        return self._session.scalar(select(StoreMembership).where(StoreMembership.store_id == store_id, StoreMembership.user_id == user_id))

    def list_memberships_for_store(self, store_id: UUID) -> list[StoreMembership]:
        return list(self._session.scalars(select(StoreMembership).where(StoreMembership.store_id == store_id).order_by(StoreMembership.user_id, StoreMembership.id)))


class StoreRepository:
    """New Store bootstrap and explicit Store context lookup; no global listing."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add_store(self, store: Store) -> None:
        require_new(store)
        self._session.add(store)

    def get_store_by_id(self, store_id: UUID) -> Store | None:
        return self._session.scalar(select(Store).where(Store.id == store_id))

