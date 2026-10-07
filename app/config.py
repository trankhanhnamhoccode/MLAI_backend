from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


BACKEND_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "shelfcash-backend"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://shelfcash:shelfcash@127.0.0.1:5432/shelfcash"
    test_database_url: str = "postgresql+psycopg://shelfcash:shelfcash@127.0.0.1:5432/shelfcash_test"
    runtime_directory: Path = Path("runtime")
    upload_directory: Path = Path("runtime/uploads")
    model_artifact_directory: Path = Path("runtime/model_artifacts")
    openrouter_api_key: SecretStr | None = None
    openrouter_model: str | None = None

    @field_validator("database_url", "test_database_url")
    @classmethod
    def require_synchronous_postgresql(cls, value: str) -> str:
        url = make_url(value)
        if url.drivername != "postgresql+psycopg" or not url.host or not url.database:
            raise ValueError("Competition Edition requires a PostgreSQL URL with psycopg, host and database")
        return value

    @field_validator(
        "runtime_directory", "upload_directory", "model_artifact_directory"
    )
    @classmethod
    def resolve_directory(cls, value: Path) -> Path:
        return value if value.is_absolute() else BACKEND_ROOT / value
