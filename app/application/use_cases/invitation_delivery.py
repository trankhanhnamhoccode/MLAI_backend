"""Explicit local delivery command. SMTP never runs inside a DB transaction."""
from app.application.use_cases.durable_delivery import DeliveryAttempt, dispatch
from uuid import uuid4
from app.application.use_cases.provisioning import AssistedProvisioning
from app.application.use_cases.staff import delivery_identity, invitation_event
from app.infrastructure.database.auth_session import auth_session
from app.repositories.staff import StaffRepository
from app.models.staff import InvitationDeliveryIntent


class InvitationDispatcher:
    def __init__(self, engine, settings, clock):
        self.engine, self.settings, self.clock = engine, settings, clock

    def dispatch(self, operator_id, key, deliver, *, limit=100):
        """One claim per intent. Unacknowledged send/commit needs Owner reissue.

        A process crash after claim does not automatically resend an unknown SMTP
        outcome. Existing pending offers stay valid until expiry/revoke/reissue.
        No token is returned by this command or included in diagnostics.
        """
        AssistedProvisioning(self.engine, self.settings)._operator(operator_id, key)
        return dispatch(self, self.settings.auth_delivery_encryption_key, deliver, limit=limit)

    def expire(self, limit):
        # Bound retention even for a process that crashed after its claim commit.
        with auth_session(self.engine) as s:
            expired = StaffRepository(s).expired_intents(self.clock(), limit)
        for identifier in expired:
            with auth_session(self.engine) as s:
                repo = StaffRepository(s)
                observed = s.get(InvitationDeliveryIntent, identifier)
                if observed is None:
                    continue
                row = repo.invitation(observed.invitation_id, locked=True)
                intent = repo.lock_intent(identifier)
                if self.clock() >= intent.expires_at:
                    intent.ciphertext = None
                    if intent.status == "queued":
                        intent.status = "failed"
                        if row.version == intent.invitation_version:
                            row.delivery_status = "failed"
                            invitation_event(s, row, actor=None, now=self.clock(), kind="DELIVERY_FAILED", attempt=identifier)
                s.commit()

    def pending(self, limit):
        with auth_session(self.engine) as s:
            return StaffRepository(s).queued_intents(self.clock(), limit)

    def claim(self, identifier):
        with auth_session(self.engine) as s:
            repo = StaffRepository(s)
            observed = s.get(InvitationDeliveryIntent, identifier)
            if observed is None:
                return None
            row = repo.invitation(observed.invitation_id, locked=True)
            intent = repo.lock_intent(identifier)
            if intent.status != "queued" or intent.claim is not None:
                return None
            if row.status != "pending" or row.version != intent.invitation_version or self.clock() >= intent.expires_at:
                intent.status, intent.ciphertext = "failed", None
                s.commit()
                return "cancelled"
            intent.claim = uuid4()
            attempt = DeliveryAttempt(identifier, intent.claim, row.target_email, intent.ciphertext,
                                      delivery_identity(row, identifier), row.id)
            s.commit()
            return attempt

    def settle(self, attempt, outcome):
        with auth_session(self.engine) as s:
            repo = StaffRepository(s)
            current = repo.invitation(attempt.invitation_id, locked=True)
            intent = repo.lock_intent(attempt.identifier)
            if intent.claim != attempt.claim or intent.status != "queued":
                return False
            intent.status, intent.ciphertext = outcome, None
            if current.version == intent.invitation_version:
                current.delivery_status = outcome
                invitation_event(s, current, actor=None, now=self.clock(),
                    kind="DELIVERY_SUCCEEDED" if outcome == "delivered" else "DELIVERY_FAILED", attempt=attempt.identifier)
            s.commit()
            return True
