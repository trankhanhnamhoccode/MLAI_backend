"""Explicit customer-supplied Store metadata, with no business defaults."""
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import Field, StrictStr, field_validator
from app.application.contracts.auth import DTO


class StoreCreateRequest(DTO):
    name: StrictStr = Field(min_length=1,max_length=200)
    timezone: StrictStr = Field(min_length=1,max_length=64)
    currency: StrictStr = Field(min_length=3,max_length=3,pattern=r'^[A-Z]{3}$')

    @field_validator('name')
    @classmethod
    def trimmed_name(cls,value):
        if not value.strip() or any(ord(ch)<32 or ord(ch)==127 for ch in value):raise ValueError('VALIDATION_ERROR')
        return value.strip()

    @field_validator('timezone')
    @classmethod
    def known_timezone(cls,value):
        try:ZoneInfo(value)
        except (ValueError,ZoneInfoNotFoundError):raise ValueError('INVALID_TIMEZONE') from None
        return value
