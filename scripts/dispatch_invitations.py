"""Controlled one-process invitation delivery; no automatic migration or reset."""
import argparse
import getpass
from email.message import EmailMessage
import smtplib
import ssl
from urllib.parse import urlsplit, urlencode
from pydantic import SecretStr
from app.config import Settings
from app.application.use_cases.auth import now_utc
from app.application.use_cases.invitation_delivery import InvitationDispatcher
from app.infrastructure.database.engine import create_database_engine


def smtp_sender(settings):
    url = urlsplit(settings.auth_invitation_frontend_url or "")
    if (url.scheme != "https" or not url.hostname or url.username or url.password
            or url.query or url.fragment or not settings.auth_smtp_host or not settings.auth_delivery_sender):
        raise ValueError("Configure HTTPS invitation frontend and SMTP delivery before dispatch")
    def send(address, invitation_id, secret):
        message = EmailMessage()
        message["From"], message["To"], message["Subject"] = settings.auth_delivery_sender, address, "ShelfCash Staff invitation"
        fragment = urlencode(dict(invitation_id=str(invitation_id), token=secret.get_secret_value()))
        message.set_content("Sign in with your verified account to review and accept:\n" + settings.auth_invitation_frontend_url + "#" + fragment)
        with smtplib.SMTP_SSL(settings.auth_smtp_host, settings.auth_smtp_port, timeout=20, context=ssl.create_default_context()) as smtp:
            if settings.auth_smtp_username:
                smtp.login(settings.auth_smtp_username, settings.auth_smtp_password.get_secret_value() if settings.auth_smtp_password else "")
            smtp.send_message(message)
    return send


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operator-id", required=True)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    settings = Settings()
    key = SecretStr(getpass.getpass("Operator credential: "))
    sender = smtp_sender(settings)
    engine = create_database_engine(settings)
    try:
        print(InvitationDispatcher(engine, settings, now_utc).dispatch(args.operator_id, key, sender, limit=args.limit))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
