"""PLAN14 public configuration boundaries; saved values are fully resolved."""
from typing import Annotated, Literal
from pydantic import AwareDatetime, Field, field_validator, model_serializer
from app.application.contracts.auth import DTO
from app.application.contracts.public_reads import EmptyMeta
from app.application.contracts.planning_setup import (
    CustomRequirements, StoredRequirements, ResourceId, Version, MoneyText, DefaultReference,
)


class SaveRequest(DTO):
    name: Annotated[str, Field(strict=True, min_length=1, max_length=200)]
    requirements: CustomRequirements
    default_requirements_version: Version | None = None

    @field_validator('name', mode='before')
    @classmethod
    def name_content(cls, value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError('INVALID_NAME')
        return value.strip()

    @field_validator('default_requirements_version', mode='before')
    @classmethod
    def nonnull_version(cls, value):
        if value is None:
            raise ValueError('DEFAULT_VERSION_REQUIRED')
        return value


class ReplaceRequest(SaveRequest):
    state: Literal['active']


class ArchiveRequest(DTO):
    state: Literal['archived']


class BudgetRequest(DTO):
    amount: MoneyText


class Validation(DTO):
    status: Literal['valid', 'invalid', 'unknown']
    reason_codes: tuple[str, ...]


class NotificationDetails(DTO):
    default_updated_at: AwareDatetime | None = None
    saved_updated_at: AwareDatetime | None = None


class PlanningConfigurationNotification(DTO):
    code: str
    message: str
    details: NotificationDetails


Notification=PlanningConfigurationNotification


class SavedDetail(DTO):
    saved_requirement_id: ResourceId
    store_id: ResourceId
    name: str
    version: Version
    state: Literal['active', 'archived']
    created_at: AwareDatetime
    updated_at: AwareDatetime
    created_by_user_id: ResourceId
    updated_by_user_id: ResourceId
    requirements: StoredRequirements
    default_reference: DefaultReference | None
    validation: Validation
    warnings: tuple[Notification, ...]


class BudgetCeiling(DTO):
    amount: MoneyText
    currency: str
    version: Version
    updated_at: AwareDatetime


class BudgetResult(DTO):
    store_id: ResourceId
    budget_ceiling: BudgetCeiling


class FieldError(DTO):
    code: str
    field: str
    message: str


class ConfigurationError(Exception):
    def __init__(self, code, status=422, field_errors=()):
        super().__init__(code)
        self.code, self.status, self.field_errors = code, status, tuple(field_errors)


class ConfigurationErrorDetails(DTO):
    field_errors: tuple[FieldError,...] | None = None
    approval_request_allowed: Literal[False] | None = None

    @model_serializer(mode='wrap')
    def serialize(self,handler):
        return {k:v for k,v in handler(self).items() if v is not None}


class ConfigurationErrorInfo(DTO):
    code: str
    message: str
    details: ConfigurationErrorDetails


class ConfigurationErrorEnvelope(DTO):
    data: None
    meta: EmptyMeta
    error: ConfigurationErrorInfo
