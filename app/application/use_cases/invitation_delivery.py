"""Explicit local delivery command. SMTP never runs inside a DB transaction."""
import logging
from uuid import uuid4
from app.application.use_cases.provisioning import AssistedProvisioning
from app.application.use_cases.staff import delivery_identity, invitation_event
from app.infrastructure.database.auth_session import auth_session
from app.infrastructure.invitation_secret import InvitationSecret
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
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Invalid dispatch limit")
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
        with auth_session(self.engine) as s:
            identifiers = StaffRepository(s).queued_intents(self.clock(), limit)
        counts = dict(delivered=0, failed=0, cancelled=0)
        for identifier in identifiers:
            with auth_session(self.engine) as s:
                repo = StaffRepository(s)
                observed = s.get(InvitationDeliveryIntent, identifier)
                if observed is None:
                    continue
                row = repo.invitation(observed.invitation_id, locked=True)
                intent = repo.lock_intent(identifier)
                if intent.status != "queued" or intent.claim is not None:
                    continue
                if row.status != "pending" or row.version != intent.invitation_version or self.clock() >= intent.expires_at:
                    intent.status, intent.ciphertext = "failed", None
                    counts["cancelled"] += 1
                    s.commit()
                    continue
                claim = uuid4()
                intent.claim = claim
                ciphertext, identity, address = intent.ciphertext, delivery_identity(row, identifier), row.target_email
                issuance_version = row.version
                s.commit()
            try:
                secret = InvitationSecret(self.settings.auth_delivery_encryption_key).open(ciphertext, identity)
                deliver(address, row.id, secret)
                outcome = "delivered"
            except Exception as error:
                # Provider details can contain credentials/address/token. Class only.
                logging.getLogger(__name__).warning("Invitation delivery not confirmed (%s)", type(error).__name__)
                outcome = "failed"
            with auth_session(self.engine) as s:
                repo = StaffRepository(s)
                current = repo.invitation(row.id, locked=True)
                intent = repo.lock_intent(identifier)
                if intent.claim != claim or intent.status != "queued":
                    # Concurrent revoke/reissue/accept cancelled this attempt.
                    counts["cancelled"] += 1
                    continue
                intent.status, intent.ciphertext = outcome, None
                if current.version == issuance_version:
                    current.delivery_status = outcome
                    invitation_event(s, current, actor=None, now=self.clock(),
                        kind="DELIVERY_SUCCEEDED" if outcome == "delivered" else "DELIVERY_FAILED", attempt=identifier)
                s.commit()
            counts[outcome] += 1
        return counts
