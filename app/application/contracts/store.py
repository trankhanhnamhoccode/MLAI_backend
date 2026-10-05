from typing import Annotated
from uuid import UUID
from pydantic import StringConstraints
from app.application.contracts.common import Contract, Name


class CreateStoreInput(Contract):
    name: Name
    timezone: Annotated[str, StringConstraints(min_length=1, max_length=64, pattern=r'\S')] = 'Asia/Ho_Chi_Minh'
    currency: Annotated[str, StringConstraints(pattern=r'^[A-Z]{3}$')] = 'VND'
    active: bool = True


class GetStoreInput(Contract):
    store_id: UUID


class StoreResult(CreateStoreInput):
    id: UUID
