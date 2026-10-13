"""Offline transport configuration and email formatting; never contacts SMTP."""
import base64
import pytest
from pydantic import SecretStr
from app.config import Settings
from app.infrastructure.email_verification_transport import VerificationEmailTransport


def configured(**overrides):
    return Settings(_env_file=None, auth_allowed_origins=["https://fe.example.test"],
        **(dict(auth_email_delivery_enabled=True, auth_smtp_host="smtp.fixture.test", auth_delivery_sender="fixture@example.test",
            auth_verification_frontend_url="https://fe.example.test/verify-email",
            auth_delivery_encryption_key=SecretStr(base64.b64encode(b"k" * 32).decode())) | overrides))


@pytest.mark.parametrize("overrides", [
    {"auth_email_delivery_enabled": False}, {"auth_smtp_host": None}, {"auth_delivery_encryption_key": None},
    {"auth_delivery_encryption_key": SecretStr("invalid")},
    {"auth_verification_frontend_url": "https://evil.example.test/verify"},
    {"auth_verification_frontend_url": "https://fe.example.test/verify#token=unsafe"},
    {"auth_verification_frontend_url": "https://fe.example.test/verify?redirect=unsafe"},
    {"auth_verification_frontend_url": "http://fe.example.test/verify"},
])
def test_unconfigured_delivery_is_service_wide_unavailable(overrides):
    assert not VerificationEmailTransport(configured(**overrides)).available


def test_fake_tls_smtp_uses_configured_fragment_plaintext_and_no_client_redirect(monkeypatch):
    messages = []
    class FakeSMTP:
        def __init__(self, host, port, **kwargs):
            assert host == "smtp.fixture.test" and port == 465 and kwargs["timeout"] == 15
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def send_message(self, message): messages.append(message)
    monkeypatch.setattr("app.infrastructure.credential_delivery.smtplib.SMTP_SSL", FakeSMTP)
    transport = VerificationEmailTransport(configured())
    assert transport.available
    transport("fixture@example.test", SecretStr("synthetic-secret"))
    message = messages[0]
    assert message["To"] == "fixture@example.test" and message.get_content_type() == "text/plain"
    assert "https://fe.example.test/verify-email#token=synthetic-secret" in message.get_content()


@pytest.mark.parametrize("reset_url", [None, "http://fe.example.test/reset", "https://evil.example.test/reset", "https://fe.example.test/reset?redirect=unsafe", "https://fe.example.test/reset#token=unsafe"])
def test_reset_capability_is_independent_of_verification_url(reset_url):
    settings = configured(auth_password_reset_frontend_url=reset_url)
    assert VerificationEmailTransport(settings).available
    assert not VerificationEmailTransport(settings, purpose="RESET").available


def test_reset_fake_smtp_uses_only_configured_reset_fragment(monkeypatch):
    messages = []
    class FakeSMTP:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def send_message(self, message): messages.append(message)
    monkeypatch.setattr("app.infrastructure.credential_delivery.smtplib.SMTP_SSL", FakeSMTP)
    transport = VerificationEmailTransport(configured(auth_password_reset_frontend_url="https://fe.example.test/reset"), purpose="RESET")
    assert transport.available
    transport("holder@example.test", SecretStr("synthetic-reset-secret"))
    assert messages[0]["To"] == "holder@example.test"
    assert "https://fe.example.test/reset#token=synthetic-reset-secret" in messages[0].get_content()
    assert "verify-email" not in messages[0].get_content()
