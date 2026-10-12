"""Untrusted suggestions only; neither approval nor normalized business facts."""

from typing import Annotated, Literal
from pydantic import Field, StrictInt, StrictStr, StrictFloat, model_validator
from app.application.contracts.import_mapping import Schema
from app.application.contracts.import_scalars import ImportDTO

Confidence = Annotated[StrictFloat, Field(ge=0, le=1, allow_inf_nan=False)]


class ColumnProposal(ImportDTO):
    source_column_index: Annotated[StrictInt, Field(ge=0, le=255)]
    target_field: Annotated[StrictStr, Field(max_length=128)] | None
    confidence: Confidence | None


class SheetSuggestion(ImportDTO):
    version: Literal["sheet_suggestion/1"]
    sheet_type: Schema | None
    columns: Annotated[tuple[ColumnProposal, ...], Field(max_length=32)]
    confidence: Confidence | None
    warnings: Annotated[
        tuple[Annotated[StrictStr, Field(max_length=200)], ...], Field(max_length=8)
    ]

    @model_validator(mode="after")
    def coherent(self):
        indices = [c.source_column_index for c in self.columns]
        targets = [c.target_field for c in self.columns if c.target_field is not None]
        if len(indices) != len(set(indices)) or len(targets) != len(set(targets)):
            raise ValueError("DUPLICATE_PROPOSAL")
        if any(t.split(".")[0] != self.sheet_type for t in targets):
            raise ValueError("TARGET_OUTSIDE_SELECTED_SCHEMA")
        return self
