"""No raw credential/token persistence or logging."""
import hashlib
import hmac
import secrets

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError

HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, type=Type.ID)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class CursorSigner:
    """Owned process-private key; domain/session binding, never caller signing key."""

    def __init__(self):
        self._key = secrets.token_bytes(32)

    def sign(self, session: str, domain: str, payload: str) -> str:
        message = (domain + "\0" + session + "\0" + payload).encode("utf-8")
        return hmac.new(self._key, message, hashlib.sha256).hexdigest()


def verify_password(encoded: str, password: str) -> bool:
    try:
        return HASHER.verify(encoded, password)
    except (InvalidHashError, VerificationError):
        return False
