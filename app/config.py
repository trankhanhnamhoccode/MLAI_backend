from pathlib import Path
from typing import Literal

from pydantic import SecretStr, Field, field_validator, model_validator
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
    summary_llm_enabled: bool = False
    summary_model: str | None = None
    summary_providers: tuple[str,...] = ()
    summary_max_tokens: int = Field(default=256,ge=64,le=1024)
    summary_input_bytes: int = Field(default=16000,ge=1000,le=64000)
    summary_timeout_seconds: float = Field(default=20,gt=0,le=30)
    summary_deadline_seconds: float = Field(default=25,gt=0,le=60)
    import_llm_suggestions_enabled: bool = False
    openrouter_model: str | None = None
    openrouter_mapping_model: Literal["qwen/qwen3.5-9b"] = "qwen/qwen3.5-9b"
    openrouter_mapping_timeout_seconds: float = Field(default=30, gt=0, le=30)
    openrouter_mapping_deadline_seconds: float = Field(default=60, gt=0, le=60)
    openrouter_mapping_sample_limit: int = Field(default=8, ge=1, le=8)
    openrouter_mapping_max_tokens: int = Field(default=1800, ge=128, le=1800)
    openrouter_mapping_providers: tuple[str, ...] = ()
    import_worker_enabled: bool = False
    planning_worker_enabled: bool = False
    pdf_export_worker_enabled: bool = False
    notification_worker_enabled: bool = False
    auth_allowed_origins: list[str] = []
    auth_dev_cookie: bool = False
    auth_operator_id: str | None = None
    auth_operator_key: SecretStr | None = None
    auth_smtp_host: str | None = None
    auth_smtp_port: int = 465
    auth_smtp_username: str | None = None
    auth_smtp_password: SecretStr | None = None
    auth_delivery_sender: str | None = None
    auth_frontend_url: str | None = None
    auth_invitation_frontend_url: str | None = None
    auth_delivery_encryption_key: SecretStr | None = None
    auth_email_delivery_enabled: bool = False
    auth_verification_frontend_url: str | None = None
    auth_password_reset_frontend_url: str | None = None

    @model_validator(mode="after")
    def auth_transport(self):
        from urllib.parse import urlsplit
        if self.auth_dev_cookie and self.environment not in {"development", "test"}:
            raise ValueError("Dev cookies cannot be used in production")
        for origin in self.auth_allowed_origins:
            parts = urlsplit(origin)
            if "*" in origin or parts.scheme not in {"https", "http"} or not parts.hostname or parts.username or parts.password or parts.path or parts.query or parts.fragment:
                raise ValueError("Auth origins must be exact scheme/host/port")
            if parts.scheme != "https" and parts.hostname not in {"localhost", "127.0.0.1", "::1"}:
                raise ValueError("HTTP auth origins must be loopback")
        return self

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
