"""Canonical Store-scoped discovery reads; caller owns the snapshot."""
from sqlalchemy import select
from sqlalchemy.orm import Session
from uuid import UUID
from app.models import Supplier
from app.models import StoreMembership, User
from app.models.auth import MembershipGrant
from app.models.collaboration import PermissionRequestRecord, MappingSubmissionRecord
from app.models.import_staging import ImportBatch, ImportProfile, ImportAudit, ImportJob


def supplier_identities(session: Session, store: UUID):
    return tuple(dict(row) for row in session.execute(select(
        Supplier.id, Supplier.name, Supplier.active, Supplier.updated_at)
        .where(Supplier.store_id == store)).mappings())


def import_task_sources(session: Session, store: UUID, actor: UUID | None):
    query=select(ImportBatch).where(ImportBatch.store_id==store)
    if actor is not None:query=query.where(ImportBatch.actor_id==actor)
    batches=tuple(session.scalars(query))
    ids={b.id for b in batches}
    profiles=tuple(session.scalars(select(ImportProfile).where(ImportProfile.store_id==store,ImportProfile.import_id.in_(ids)))) if ids else ()
    audit=tuple(session.scalars(select(ImportAudit).where(ImportAudit.store_id==store))) if ids else ()
    jobs=tuple(session.scalars(select(ImportJob).where(ImportJob.store_id==store,ImportJob.import_id.in_(ids)))) if ids else ()
    return batches,profiles,audit,jobs


def mapping_tasks(session: Session,store: UUID,actor: UUID | None):
    query=select(MappingSubmissionRecord,ImportBatch,ImportProfile).join(ImportBatch,
        ImportBatch.id==MappingSubmissionRecord.import_id).join(ImportProfile,ImportProfile.id==MappingSubmissionRecord.profile_id)
    query=query.where(MappingSubmissionRecord.store_id==store,ImportBatch.store_id==store,ImportProfile.store_id==store)
    if actor is not None:query=query.where(MappingSubmissionRecord.submitted_by_user_id==actor)
    return tuple(session.execute(query))


def permission_tasks(session: Session,store: UUID,actor: UUID | None):
    query=select(PermissionRequestRecord,StoreMembership,User.active).join(StoreMembership,
        StoreMembership.id==PermissionRequestRecord.requester_membership_id).join(User,User.id==PermissionRequestRecord.requester_user_id)
    query=query.where(PermissionRequestRecord.store_id==store,StoreMembership.store_id==store,PermissionRequestRecord.state=='pending')
    if actor is not None:query=query.where(PermissionRequestRecord.requester_user_id==actor)
    records=tuple(session.execute(query))
    ids={member.id for _,member,_ in records}
    grants={identity:[] for identity in ids}
    if ids:
        for identity,key in session.execute(select(MembershipGrant.membership_id,MembershipGrant.permission).where(MembershipGrant.membership_id.in_(ids))):
            grants[identity].append(key)
    return records,grants
