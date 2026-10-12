"""Explicit supported operator BASELINE/default setup. No auto activation/training."""
import argparse
import getpass
import json
from pathlib import Path
from pydantic import SecretStr
from app.config import Settings
from app.application.contracts.model_serving import OperatorConfigurationCommand
from app.application.use_cases.model_serving import ModelServingOperator
from app.application.use_cases.auth import now_utc
from app.infrastructure.database.engine import create_database_engine


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--command-file',type=Path,required=True)
    args=parser.parse_args()
    settings=Settings()
    command=OperatorConfigurationCommand.model_validate(json.loads(args.command_file.read_text(encoding='utf-8')))
    key=SecretStr(getpass.getpass('Operator credential: '))
    engine=create_database_engine(settings)
    try:
        value=ModelServingOperator(engine,settings,now_utc).configure(command,settings.auth_operator_id,key)
        print(value.model_dump_json() if hasattr(value,'model_dump_json') else json.dumps({'version':value}))
    except Exception:
        print('Planning configuration failed; inspect current versions before retry.');return 1
    finally:engine.dispose()
    return 0


if __name__=='__main__':
    raise SystemExit(main())
