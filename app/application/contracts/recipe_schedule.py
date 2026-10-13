"""Exact CAT12 N20–N22 wire and retained boundaries."""
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID
from pydantic import Field, StrictStr, StrictInt, field_validator, model_validator
from app.application.contracts.import_scalars import ImportDTO as DTO, Text

Quantity = Annotated[StrictStr, Field(pattern=r"^(0|[1-9][0-9]*)(\.[0-9]+)?$")]


def positive(value):
    if Decimal(value) <= 0:
        raise ValueError("INVALID_RECIPE_CONTENT")
    return value


class LineInput(DTO):
    ingredient_id: UUID
    quantity: Quantity
    unit: Annotated[StrictStr, Field(min_length=1, max_length=32, pattern=r"\S")]

    _positive = field_validator("quantity")(positive)


class ContentLine(LineInput):
    recipe_line_id: UUID


class Content(DTO):
    recipe_id: UUID
    version: StrictInt = Field(ge=1, le=2147483647)
    yield_quantity: Quantity
    yield_unit: str
    process_loss_rate: Quantity
    ingredients: tuple[ContentLine, ...]

    _positive = field_validator("yield_quantity")(positive)

    @field_validator("process_loss_rate")
    @classmethod
    def loss(cls, value):
        if Decimal(value) >= 1:
            raise ValueError("INVALID_RECIPE_CONTENT")
        return value


class Assignment(DTO):
    effective_from: date
    effective_to: date | None


class ScheduleItem(DTO):
    content: Content
    assignment: Assignment | None
    state: Literal["past", "in_effect", "scheduled", "unassigned"]


class NewRecipe(DTO):
    client_reference: Annotated[StrictStr, Field(min_length=1, max_length=64, pattern=r"\S")]
    yield_quantity: Quantity
    yield_unit: Annotated[StrictStr, Field(min_length=1, max_length=32, pattern=r"\S")]
    process_loss_rate: Quantity
    ingredients: Annotated[tuple[LineInput, ...], Field(min_length=1, max_length=100)]

    _positive = field_validator("yield_quantity")(positive)
    _loss = field_validator("process_loss_rate")(Content.loss.__func__)

    @model_validator(mode="after")
    def unique_lines(self):
        if len({l.ingredient_id for l in self.ingredients}) != len(self.ingredients):
            raise ValueError("INVALID_RECIPE_CONTENT")
        return self


class ExistingRef(DTO):
    recipe_id: UUID


class NewRef(DTO):
    new_recipe_reference: Annotated[StrictStr, Field(min_length=1, max_length=64, pattern=r"\S")]


class SetPeriod(DTO):
    kind: Literal["SET_PERIOD"]
    recipe_ref: ExistingRef | NewRef
    effective_from: date
    effective_to: date | None


class Withdraw(DTO):
    kind: Literal["WITHDRAW_FUTURE"]
    recipe_ref: ExistingRef


Operation = Annotated[SetPeriod | Withdraw, Field(discriminator="kind")]


class PreviewRequest(DTO):
    phase: Literal["preview"]
    new_recipes: Annotated[tuple[NewRecipe, ...], Field(max_length=20)]
    operations: Annotated[tuple[Operation, ...], Field(max_length=100)]
    reason: Text


class CommitRequest(DTO):
    phase: Literal["commit"]
    change_id: UUID
    preview_digest: Annotated[StrictStr, Field(min_length=1, max_length=128)]
    confirm: Literal[True]
    acknowledged_warning_codes: Annotated[tuple[StrictStr, ...], Field(max_length=100)]

    @field_validator("confirm", mode="before")
    @classmethod
    def explicit_true(cls, value):
        if value is not True:
            raise ValueError("EXPLICIT_TRUE_REQUIRED")
        return value


class DateRange(DTO):
    from_date: date
    to_date: date | None


class NoticeDetails(DTO):
    entity: Literal["product", "ingredient"]
    entity_id: UUID
    field: str
    affected_dates: tuple[date, ...] = ()
    affected_ranges: tuple[DateRange, ...] = ()


class Notification(DTO):
    code: str
    message: str
    details: NoticeDetails


class Timeline(DTO):
    store_id: UUID
    product_id: UUID
    as_of_date: date
    schedule_version: str
    catalog_version: str
    items: tuple[ScheduleItem, ...]
    minimum_change_date: date


class Preview(DTO):
    change_id: UUID
    status: Literal["preview_ready", "blocked"]
    preview_digest: str
    store_id: UUID
    product_id: UUID
    evaluated_at: datetime
    as_of_date: date
    minimum_change_date: date
    schedule_version: str
    catalog_version: str
    before: tuple[ScheduleItem, ...]
    after: tuple[ScheduleItem, ...]
    changed_ranges: tuple[DateRange, ...]
    new_contents: tuple[Content, ...]
    required_permissions: tuple[str, ...]
    blockers: tuple[Notification, ...]
    warnings: tuple[Notification, ...]
    required_warning_acknowledgements: tuple[str, ...]
    can_commit: bool


class UpdatedResources(DTO):
    menu: bool
    recipes: bool
    inventory: Literal[False] = False
    sales: Literal[False] = False
    forecast: Literal[False] = False
    retained_runs: Literal[False] = False


class Receipt(DTO):
    change_id: UUID
    status: Literal["committed"] = "committed"
    preview_digest: str
    store_id: UUID
    product_id: UUID
    committed_at: datetime
    schedule_version_before: str
    schedule_version_after: str
    created_recipe_ids: tuple[UUID, ...]
    affected_recipe_ids: tuple[UUID, ...]
    audit_reference: UUID
    changed: bool
    updated_resources: UpdatedResources
    warnings: tuple[Notification, ...]


class Audit(DTO):
    change_id: UUID
    actor_user_id: UUID
    store_id: UUID
    product_id: UUID
    reason: Text
    occurred_at: datetime
    preview_digest: str
    calendar_before_version: str
    calendar_after_version: str
    before: tuple[ScheduleItem, ...]
    after: tuple[ScheduleItem, ...]
    new_content_ids: tuple[UUID, ...]
    operations: tuple[Operation, ...]
    acknowledged_warnings: tuple[str, ...]
    request_id: str


class ChangeRead(DTO):
    change_id: UUID
    status: Literal["preview_ready", "blocked", "committed"]
    preview: Preview
    receipt: Receipt | None
    audit: Audit | None
