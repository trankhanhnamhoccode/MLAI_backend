"""Detached immutable physical source facts; no canonical promotion or identity."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class SourceCell:
    column_index: int
    raw: str | None
    kind: Literal["text", "numeric", "boolean", "date", "empty", "error"]
    formula: bool = False


@dataclass(frozen=True)
class SourceRow:
    row_number: int
    cells: tuple[SourceCell, ...]
    record_number: int | None = None
    line_start: int | None = None
    line_end: int | None = None


@dataclass(frozen=True)
class ParsedSheet:
    name: str
    index: int
    rows: tuple[SourceRow, ...]


@dataclass(frozen=True)
class ParsedFile:
    format: Literal["csv", "xlsx"]
    sheets: tuple[ParsedSheet, ...]
    warnings: tuple[str, ...] = ()


class SourceParseError(ValueError):
    """Sanitized code and physical location, never raw input or provider errors."""

    def __init__(
        self,
        code: str,
        *,
        sheet: str | None = None,
        row: int | None = None,
        column: int | None = None
    ):
        self.code, self.sheet, self.row, self.column = code, sheet, row, column
        super().__init__(code)
