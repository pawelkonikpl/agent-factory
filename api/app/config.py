"""Resource server configuration, read from environment variables with the API_ prefix."""

from cryptography.fernet import Fernet
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # hide_input_in_errors: a rejected value, such as the encryption key, is never printed.
    model_config = SettingsConfigDict(
        env_prefix="API_", env_file=".env", extra="ignore", hide_input_in_errors=True
    )

    issuer: str = "http://localhost:8080/realms/demo"
    # Tokens must name this API in "aud" (RFC 9700: audience-restricted access tokens).
    audience: str = "demo-api"
    http_timeout_seconds: float = 5.0
    jwks_min_refresh_interval_seconds: float = 60.0
    database_url: str = "postgresql+asyncpg://emailsender:emailsender@localhost:5432/emailsender"
    # Tests only: the database tests/conftest.py uses (its name must contain "test").
    test_database_url: str | None = None
    # Sends at once per campaign when POST /campaigns/{id}/send gives no max_concurrent (D10).
    email_max_concurrent: int = Field(10, ge=1, le=50)
    # Seeds the demo clients and campaigns at startup, idempotently (D22). Dev only.
    seed_demo_data: bool = False
    # Encrypts the stored SMTP passwords. Required: the API does not start without it.
    encryption_key: SecretStr

    @field_validator("encryption_key")
    @classmethod
    def check_encryption_key(cls, value: SecretStr) -> SecretStr:
        try:
            Fernet(value.get_secret_value())
        except ValueError:
            raise ValueError(
                "API_ENCRYPTION_KEY must be a valid Fernet key (32 url-safe base64-encoded bytes)"
            ) from None
        return value
