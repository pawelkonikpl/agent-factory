"""BFF configuration, read from environment variables with the BFF_ prefix."""

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

SESSION_COOKIE_BASE_NAME = "bff-session"
LOGIN_COOKIE_BASE_NAME = "bff-login"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BFF_", env_file=".env", extra="ignore")

    issuer: str = "http://localhost:8080/realms/demo"
    client_id: str = "demo-bff"
    client_secret: SecretStr
    scope: str = "openid profile email"
    redirect_uri: str = "http://localhost:5173/bff/callback"
    post_logout_redirect_uri: str = "http://localhost:5173/"
    app_origin: str = "http://localhost:5173"
    # The only resource server the proxy may call (RFC 10017: strict outbound control).
    api_base_url: str = "http://localhost:8001"
    cookie_secure: bool = True
    login_timeout_seconds: int = 10 * 60
    session_idle_timeout_seconds: int = 30 * 60
    session_absolute_timeout_seconds: int = 8 * 60 * 60
    token_refresh_margin_seconds: int = 30
    http_timeout_seconds: float = 10.0

    @property
    def session_cookie_name(self) -> str:
        return _cookie_name(SESSION_COOKIE_BASE_NAME, secure=self.cookie_secure)

    @property
    def login_cookie_name(self) -> str:
        return _cookie_name(LOGIN_COOKIE_BASE_NAME, secure=self.cookie_secure)


def _cookie_name(base_name: str, *, secure: bool) -> str:
    # "__Host-" makes browsers reject the cookie unless it is Secure, has Path=/ and no
    # Domain, so a sibling subdomain cannot plant or overwrite it. "__Host-Http-" is the
    # prefix RFC 10017 uses as an example; browsers that know it also demand HttpOnly.
    # Prefixed cookies must be Secure, so plain HTTP setups fall back to a bare name.
    return f"__Host-Http-{base_name}" if secure else base_name
