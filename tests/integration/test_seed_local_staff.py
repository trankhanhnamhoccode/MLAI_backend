"""Staff fixtures retain real invitation consent, audit and current authorization."""
import base64

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application.contracts.auth import AuthError
from app.application.use_cases.staff import StaffUseCases
from app.infrastructure.database.engine import create_database_engine
from app.models import Store, StoreMembership
from app.models.auth import AuthAccount, AuthSession, MembershipGrant
from app.models.staff import StaffInvitation, PermissionEventRecord, InvitationDeliveryIntent
from scripts.seed_local_staff import seed_staff


def test_staff_invitation_recovery_replay_and_revocation(database_settings, tmp_path, monkeypatch):
    settings = database_settings.model_copy(update={
        "auth_delivery_encryption_key": SecretStr(base64.b64encode(b"s" * 32).decode())})
    engine = create_database_engine(settings)
    accept = StaffUseCases.accept
    def interrupted(*args, **kwargs):
        raise RuntimeError("synthetic interruption before acceptance")
    try:
        monkeypatch.setattr(StaffUseCases, "accept", interrupted)
        with pytest.raises(RuntimeError):
            seed_staff(engine, settings, tmp_path)
        with Session(engine) as fresh:
            assert fresh.scalar(select(func.count()).select_from(StoreMembership)) == 1
            assert fresh.scalar(select(StaffInvitation)).status == "pending"
        monkeypatch.setattr(StaffUseCases, "accept", accept)
        staff = seed_staff(engine, settings, tmp_path)
        original = (tmp_path / "test-staff.json").read_bytes()
        assert staff.membership.role == "STAFF"
        assert staff.membership.effective_permissions == ("menu.read",)
        assert seed_staff(engine, settings, tmp_path).membership.membership_id == staff.membership.membership_id
        with Session(engine) as fresh:
            assert fresh.scalar(select(func.count()).select_from(Store)) == 1
            assert fresh.scalar(select(func.count()).select_from(StoreMembership)) == 2
            assert fresh.scalar(select(func.count()).select_from(StaffInvitation)) == 1
            invitation = fresh.scalar(select(StaffInvitation))
            assert invitation.status == "accepted" and invitation.accepted_at
            assert all(a.credential_ready for a in fresh.scalars(select(AuthAccount)))
            assert all(s.revoked_at for s in fresh.scalars(select(AuthSession)))
            event = fresh.scalar(select(PermissionEventRecord).where(
                PermissionEventRecord.membership_id == staff.membership.membership_id))
            assert event.record_json["source"] == "INVITATION_ACCEPTANCE"
            assert event.record_json["after_grants"] == ["menu.read"]
            assert fresh.scalar(select(InvitationDeliveryIntent)).ciphertext is None
        # Re-running preserves revoked grants and inactive membership.
        with Session(engine) as session:
            session.delete(session.get(MembershipGrant, (staff.membership.membership_id, "menu.read")))
            session.commit()
        assert seed_staff(engine, settings, tmp_path).membership.effective_permissions == ()
        with Session(engine) as session:
            session.get(StoreMembership, staff.membership.membership_id).active = False
            session.commit()
        with pytest.raises(AuthError):
            seed_staff(engine, settings, tmp_path)
        with Session(engine) as fresh:
            assert not fresh.get(StoreMembership, staff.membership.membership_id).active
            assert fresh.scalar(select(func.count()).select_from(StaffInvitation)) == 1
        assert (tmp_path / "test-staff.json").read_bytes() == original
    finally:
        engine.dispose()
