"""Shared bounded local dispatch for invitation and verification intents."""
from dataclasses import dataclass, field
from typing import Callable, Literal, Protocol
from uuid import UUID
from pydantic import SecretStr
from app.infrastructure.invitation_secret import InvitationSecret


@dataclass(frozen=True)
class DeliveryAttempt:
    identifier: UUID
    claim: UUID
    address: str
    ciphertext: bytes = field(repr=False)
    identity: str
    invitation_id: UUID | None = None


class DeliveryQueue(Protocol):
    def expire(self, limit: int) -> None: ...
    def pending(self, limit: int) -> tuple[UUID, ...]: ...
    def claim(self, identifier: UUID) -> DeliveryAttempt | Literal["cancelled"] | None: ...
    def settle(self, attempt: DeliveryAttempt, outcome: str) -> bool: ...


def dispatch(queue: DeliveryQueue, key: SecretStr | None, deliver: Callable, *, limit: int = 100):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Invalid dispatch limit")
    queue.expire(limit)
    counts = dict(delivered=0, failed=0, cancelled=0)
    for identifier in queue.pending(limit):
        attempt = queue.claim(identifier)
        if attempt is None:
            continue
        if attempt == "cancelled":
            counts["cancelled"] += 1
            continue
        # Claim transaction is closed before decryption or transport.
        try:
            secret = InvitationSecret(key).open(attempt.ciphertext, attempt.identity)
            if attempt.invitation_id is None:
                deliver(attempt.address, secret)
            else:
                deliver(attempt.address, attempt.invitation_id, secret)
            outcome = "delivered"
        except Exception:
            # Provider diagnostics may contain secret/address data.
            outcome = "failed"
        counts[outcome if queue.settle(attempt, outcome) else "cancelled"] += 1
    return counts
