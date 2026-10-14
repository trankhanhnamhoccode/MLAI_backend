"""Controlled one-process invitation delivery; no automatic migration or reset."""
import argparse
import getpass
from pydantic import SecretStr
from app.config import Settings
from app.application.use_cases.auth import now_utc
from app.application.use_cases.invitation_delivery import InvitationDispatcher
from app.infrastructure.database.engine import create_database_engine


from app.infrastructure.invitation_email import smtp_sender


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operator-id", required=True)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    settings = Settings()
    if settings.auth_email_delivery_enabled:
        raise ValueError("The enabled application email worker owns this queue; do not start a second dispatcher")
    key = SecretStr(getpass.getpass("Operator credential: "))
    sender = smtp_sender(settings)
    engine = create_database_engine(settings)
    try:
        print(InvitationDispatcher(engine, settings, now_utc).dispatch(args.operator_id, key, sender, limit=args.limit))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
