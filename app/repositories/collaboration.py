"""Concrete C2 queries; callers retain authority fences and transaction ownership."""
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import User,StoreMembership
from app.models.collaboration import PermissionRequestRecord,MappingSubmissionRecord
from app.models.import_staging import ImportProfile


class CollaborationRepository:
    def __init__(self, session: Session):
        self.session=session

    def active_owners(self, store: UUID) -> tuple[UUID,...]:
        return tuple(self.session.scalars(select(User.id).join(StoreMembership,StoreMembership.user_id==User.id)
            .where(StoreMembership.store_id==store,StoreMembership.active.is_(True),
                StoreMembership.role=='OWNER',User.active.is_(True)).order_by(User.id)))

    def pending_requests(self, member: UUID):
        return self.session.scalars(select(PermissionRequestRecord).where(
            PermissionRequestRecord.requester_membership_id==member,PermissionRequestRecord.state=='pending').with_for_update()).all()

    def pending_request(self, store: UUID, member: UUID):
        return self.session.scalar(select(PermissionRequestRecord).where(PermissionRequestRecord.store_id==store,
            PermissionRequestRecord.requester_membership_id==member,PermissionRequestRecord.state=='pending'))

    def request(self, identity: UUID, store: UUID, requester: UUID | None):
        query=select(PermissionRequestRecord).where(PermissionRequestRecord.id==identity,PermissionRequestRecord.store_id==store)
        if requester is not None: query=query.where(PermissionRequestRecord.requester_user_id==requester)
        return self.session.scalar(query.with_for_update())

    def requests(self, store: UUID, requester: UUID | None):
        query=select(PermissionRequestRecord).where(PermissionRequestRecord.store_id==store)
        if requester is not None: query=query.where(PermissionRequestRecord.requester_user_id==requester)
        return self.session.scalars(query.order_by(PermissionRequestRecord.created_at.desc(),PermissionRequestRecord.id)).all()

    def pending_submissions(self, store: UUID):
        return self.session.scalars(select(MappingSubmissionRecord).where(MappingSubmissionRecord.store_id==store,
            MappingSubmissionRecord.state=='submitted').order_by(MappingSubmissionRecord.id).with_for_update()).all()

    def profile(self, identity: UUID, store: UUID, import_id: UUID):
        return self.session.scalar(select(ImportProfile).where(ImportProfile.id==identity,
            ImportProfile.import_id==import_id,ImportProfile.store_id==store).with_for_update())

    def submission(self, identity: UUID, store: UUID):
        return self.session.scalar(select(MappingSubmissionRecord).where(MappingSubmissionRecord.id==identity,
            MappingSubmissionRecord.store_id==store).with_for_update())

    def live_submission(self, profile: UUID, *, locked=True):
        query=select(MappingSubmissionRecord).where(MappingSubmissionRecord.profile_id==profile,MappingSubmissionRecord.state=='submitted')
        if locked: query=query.with_for_update()
        return self.session.scalar(query)

    def submissions(self, store: UUID, submitter: UUID | None, file_id: UUID | None, import_id: UUID | None):
        query=select(MappingSubmissionRecord).where(MappingSubmissionRecord.store_id==store)
        if submitter is not None: query=query.where(MappingSubmissionRecord.submitted_by_user_id==submitter)
        if file_id is not None: query=query.where(MappingSubmissionRecord.facts['file_id'].astext==str(file_id))
        if import_id is not None: query=query.where(MappingSubmissionRecord.import_id==import_id)
        return self.session.scalars(query.order_by(MappingSubmissionRecord.submitted_at.desc(),MappingSubmissionRecord.id)).all()
