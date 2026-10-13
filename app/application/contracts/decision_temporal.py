"""Explicit /2 current-capture basis; never historical inventory evidence."""
from datetime import date
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import AwareDatetime, model_validator
from app.application.contracts.common import Contract, Nonblank


class OperationalBasis(Contract):
    version: Literal['operational_basis/1']
    kind: Literal['CURRENT_CAPTURE', 'HYPOTHETICAL_CURRENT_CAPTURE']
    captured_at: AwareDatetime
    timezone: Nonblank
    local_capture_date: date
    planning_start_date: date
    assumptions: tuple[Nonblank, ...]

    @model_validator(mode='after')
    def dates(self):
        try:
            local = self.captured_at.astimezone(ZoneInfo(self.timezone)).date()
        except (ValueError, OverflowError, ZoneInfoNotFoundError) as error:
            raise ValueError('Invalid operational capture timezone/date') from error
        kind = 'CURRENT_CAPTURE' if local == self.planning_start_date else 'HYPOTHETICAL_CURRENT_CAPTURE'
        if local != self.local_capture_date or kind != self.kind:
            raise ValueError('Operational basis must preserve actual local capture date')
        if not self.assumptions or len(set(self.assumptions)) != len(self.assumptions):
            raise ValueError('Explicit unique temporal assumptions required')
        return self
