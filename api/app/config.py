"""Resource server configuration, read from environment variables with the API_ prefix."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="API_", env_file=".env", extra="ignore")

    issuer: str = "http://localhost:8080/realms/demo"
    # Tokens must name this API in "aud" (RFC 9700: audience-restricted access tokens).
    audience: str = "demo-api"
    http_timeout_seconds: float = 5.0
    jwks_min_refresh_interval_seconds: float = 60.0
    database_url: str = "postgresql+asyncpg://emailsender:emailsender@localhost:5432/emailsender"
    # Tests only: the database tests/conftest.py uses (its name must contain "test").
    test_database_url: str | None = None
