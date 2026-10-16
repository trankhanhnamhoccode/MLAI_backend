"""Internal summary-specific clauses; never accepted from an HTTP caller."""
from typing import Literal
from pydantic import Field
from app.application.contracts.auth import DTO
from app.application.contracts.plan_summary import BlockKey


class NarrativeClause(DTO):
    fact_id: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=2000)
    evidence_ids: tuple[str, ...] = Field(min_length=1, max_length=8)


class NarrativeSection(DTO):
    family: BlockKey
    clauses: tuple[NarrativeClause, ...] = Field(min_length=1, max_length=8)


class SummaryNarrative(DTO):
    schema_version: Literal['summary_narrative/2']
    headline: NarrativeSection
    summary: NarrativeSection
    key_points: tuple[NarrativeSection, ...] = Field(min_length=3, max_length=3)
    warning_summary: NarrativeSection

    def sections(self) -> tuple[NarrativeSection, ...]:
        return (self.headline, self.summary, *self.key_points, self.warning_summary)
