"""Service-wide capability plus TLS SMTP, using the existing credential sender."""
from urllib.parse import urlsplit
from typing import Literal
from app.infrastructure.credential_delivery import SmtpCredentialDelivery
from app.infrastructure.invitation_secret import InvitationSecret


class VerificationEmailTransport:
    def __init__(self, settings, *, purpose: Literal["EMAIL_VERIFY", "RESET"] = "EMAIL_VERIFY"):
        self._sender = None
        self.enabled = settings.auth_email_delivery_enabled
        if not self.enabled:
            return
        try:
            InvitationSecret(settings.auth_delivery_encryption_key)
            frontend_url = settings.auth_verification_frontend_url if purpose == "EMAIL_VERIFY" else settings.auth_password_reset_frontend_url
            url = urlsplit(frontend_url or "")
            origin = f"{url.scheme}://{url.netloc}"
            if origin not in settings.auth_allowed_origins:
                raise ValueError("Verification frontend must use an allowed Origin")
            self._sender = SmtpCredentialDelivery(settings.model_copy(update={
                "auth_frontend_url": frontend_url}))
        except (ValueError, TypeError):
            # Misconfiguration is a global capability failure, never account specific.
            self._sender = None

    @property
    def available(self) -> bool:
        return self.enabled and self._sender is not None

    def __call__(self, address, secret):
        if not self.available:
            raise RuntimeError("Email delivery unavailable")
        self._sender(address, secret)
