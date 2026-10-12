"""Bound delivery secret: AES256-GCM; fresh96-bit nonce, revision-specific AAD."""
import base64
import secrets
from pydantic import SecretStr
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class InvitationSecret:
    def __init__(self, key: SecretStr | None):
        if not key:
            raise ValueError("Delivery encryption key required")
        raw = base64.b64decode(key.get_secret_value(), validate=True)
        if len(raw) != 32:
            raise ValueError("Delivery key must encode32 random bytes")
        self._cipher = AESGCM(raw)

    def seal(self, secret: str, identity: str) -> bytes:
        nonce = secrets.token_bytes(12)
        return nonce + self._cipher.encrypt(nonce, secret.encode(), ("invitation-delivery/1:"+identity).encode())

    def open(self, ciphertext: bytes, identity: str) -> SecretStr:
        return SecretStr(self._cipher.decrypt(ciphertext[:12], ciphertext[12:], ("invitation-delivery/1:"+identity).encode()).decode())
