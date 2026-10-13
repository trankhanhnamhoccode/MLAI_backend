"""Controlled assisted application tool; never prints credentials or raw errors.

    python -m scripts.provision_auth provision-store --command-file <verified.json>
    python -m scripts.provision_auth provision-account --command-file <verified.json>
    python -m scripts.provision_auth issue-credential --command-file <verified.json>

Operator credential entered via hidden prompt; environment contains configured
allowlisted operator identity/key. Verified evidence is required, not inferred.
"""
import argparse
import getpass
import json
from pathlib import Path
from pydantic import SecretStr
from app.application.contracts.provisioning import ProvisionStoreCommand, VerifiedAccountCommand, IssueCredentialCommand
from app.application.use_cases.provisioning import AssistedProvisioning
from app.config import Settings
from app.infrastructure.credential_delivery import SmtpCredentialDelivery
from app.infrastructure.database.engine import create_database_engine


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("provision-store", "provision-account", "issue-credential"))
    parser.add_argument("--command-file", type=Path, required=True)
    args = parser.parse_args()
    engine = None
    try:
        settings = Settings()
        if not settings.auth_operator_id or not settings.auth_operator_key:
            raise ValueError("Operator configuration required")
        key = SecretStr(getpass.getpass("Operator credential: "))
        cls = {"provision-store": ProvisionStoreCommand, "provision-account": VerifiedAccountCommand, "issue-credential": IssueCredentialCommand}[args.action]
        command = cls.model_validate(json.loads(args.command_file.read_text(encoding="utf-8")))
        # Fail configuration before any DB mutation.
        delivery = SmtpCredentialDelivery(settings) if args.action == "issue-credential" else None
        engine = create_database_engine(settings)
        service = AssistedProvisioning(engine, settings)
        result = service.issue(command, settings.auth_operator_id, key, delivery) if delivery else service.provision(command, settings.auth_operator_id, key)
        print(result.model_dump_json())
    except Exception:
        print("Assisted command failed; inspect configured channel/state before retry. No credentials logged.")
        return 1
    finally:
        if engine is not None:
            engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
