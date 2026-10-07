from sqlalchemy.orm import Session
from app.application._validation import require_idle_session
from app.application.contracts.store import CreateStoreInput, GetStoreInput, StoreResult
from app.application.errors import ApplicationError, ErrorCategory
from app.models import Store
from app.repositories.identity import StoreRepository


class StoreUseCases:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.stores = StoreRepository(session)

    def create(self, data: CreateStoreInput) -> StoreResult:
        data = CreateStoreInput.model_validate(data)
        require_idle_session(self.session)
        try:
            self.session.begin()
            row = Store(**data.model_dump())
            self.stores.add_store(row)
            self.session.flush()
            result = StoreResult.model_validate(row)
            self.session.commit()
            return result
        except Exception:
            self.session.rollback()
            raise

    def get(self, data: GetStoreInput) -> StoreResult:
        data = GetStoreInput.model_validate(data)
        with self.session.no_autoflush:
            row = self.stores.get_store_by_id(data.store_id)
            if row is None:
                raise ApplicationError(ErrorCategory.NOT_FOUND, 'Store not found')
            return StoreResult.model_validate(row)
