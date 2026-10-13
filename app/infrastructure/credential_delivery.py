"""TLS SMTP link formatter; application resolves the workflow's target address."""
from email.message import EmailMessage
import smtplib
import ssl
from urllib.parse import urlsplit
from pydantic import SecretStr
from app.config import Settings


class SmtpCredentialDelivery:
    def __init__(self, settings: Settings):
        self.settings = settings
        url = urlsplit(settings.auth_frontend_url or "")
        if not settings.auth_smtp_host or not settings.auth_delivery_sender or url.scheme != "https" or not url.hostname or url.fragment or url.query or url.username:
            raise ValueError("Verified HTTPS frontend and TLS SMTP configuration required")

    def __call__(self, verified_email: str, secret: SecretStr):
        s = self.settings
        message = EmailMessage()
        message["From"], message["To"], message["Subject"] = s.auth_delivery_sender, verified_email, "ShelfCash credential completion"
        message.set_content("Complete your credential within 30 minutes:\n" + s.auth_frontend_url + "#token=" + secret.get_secret_value())
        with smtplib.SMTP_SSL(s.auth_smtp_host, s.auth_smtp_port, context=ssl.create_default_context(), timeout=15) as client:
            if s.auth_smtp_username:
                client.login(s.auth_smtp_username, s.auth_smtp_password.get_secret_value() if s.auth_smtp_password else "")
            client.send_message(message)
