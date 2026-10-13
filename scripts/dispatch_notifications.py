"""One bounded internal dispatch batch against the explicitly configured C1 database."""
import argparse
from uuid import UUID
from app.config import Settings
from app.infrastructure.database.engine import create_database_engine
from app.application.use_cases.notification_delivery import NotificationDispatcher


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--retry-failed", type=UUID)
    args = parser.parse_args()
    engine = create_database_engine(Settings())
    try:
        dispatcher = NotificationDispatcher(engine)
        if args.retry_failed:
            dispatcher.retry_failed(args.retry_failed)
        print(f"Completed notifications: {dispatcher.dispatch(args.limit)}")
        return 0
    except Exception as error:
        print(f"Notification dispatch failed ({type(error).__name__}); private details omitted")
        return 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
