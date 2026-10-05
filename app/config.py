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
    database_url: str = "sqlite:///runtime/shelfcash.db"
    runtime_directory: Path = Path("runtime")
    upload_directory: Path = Path("runtime/uploads")
    model_artifact_directory: Path = Path("runtime/model_artifacts")
    openrouter_api_key: SecretStr | None = None
    openrouter_model: str | None = None

    @field_validator("database_url")
    @classmethod
    def require_synchronous_sqlite(cls, value: str) -> str:
        if make_url(value).drivername not in {"sqlite", "sqlite+pysqlite"}:
            raise ValueError("Competition Edition requires synchronous SQLite")
        return value

    @field_validator(
        "runtime_directory", "upload_directory", "model_artifact_directory"
    )
    @classmethod
    def resolve_directory(cls, value: Path) -> Path:
        return value if value.is_absolute() else BACKEND_ROOT / value
