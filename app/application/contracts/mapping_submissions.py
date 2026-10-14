"""C2 submission identity and immutable review pins."""
from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import model_validator
from app.application.contracts.auth import DTO
from app.application.contracts.collaboration import Reasoned, Version

State = Literal['submitted','changes_requested','approved','rejected','stale','withdrawn']


class QueueReference(DTO):
    submission_id: UUID | None=None
    expected_submission_version: Version | None=None

    @model_validator(mode='after')
    def paired(self):
        if (self.submission_id is None) != (self.expected_submission_version is None):
            raise ValueError('PAIRED_SUBMISSION_FIELDS_REQUIRED')
        return self


class SubmitMapping(Reasoned):
    action: Literal['submit']
    profile_id: UUID
    proposal_revision: Version
    mapping_revision: Version


class WithdrawMapping(Reasoned):
    action: Literal['withdraw']
    submission_id: UUID
    expected_submission_version: Version


class Eligibility(DTO):
    eligible: bool
    reason_codes: tuple[str,...]


class CurrentProfile(DTO):
    lifecycle_revision: Version
    active_version: Version | None
    reviewed_version_retired: bool


class MappingDecision(DTO):
    decision_id: UUID
    decision: Literal['approve_activate','reject','request_changes']
    actor_user_id: UUID
    reason: str
    decided_at: datetime


class MappingSubmission(DTO):
    submission_id: UUID
    store_id: UUID
    profile_id: UUID
    import_id: UUID
    sheet_id: UUID
    file_id: UUID
    submitted_by_user_id: UUID
    submitted_at: datetime
    reason: str
    version: Version
    state: State
    proposal_revision: Version
    mapping_revision: Version
    import_revision: Version
    file_set_version: Version
    lifecycle_revision_at_submission: Version
    spec_digest: Version
    expected_active_version: Version | None
    review_eligibility: Eligibility
    current_profile: CurrentProfile
    decision: MappingDecision | None
    allowed_actions: tuple[str,...]


class MappingQueue(DTO):
    items: tuple[MappingSubmission,...]
