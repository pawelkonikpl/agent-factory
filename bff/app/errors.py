"""Errors raised by the BFF. HTTP mapping lives in app/main.py."""

from enum import StrEnum


class BffError(Exception):
    """Base class for all BFF errors."""


class LoginErrorCode(StrEnum):
    """Reasons a login failed. Safe to show to the browser."""

    LOGIN_EXPIRED = "login_expired"
    STATE_MISMATCH = "state_mismatch"
    ISSUER_MISMATCH = "issuer_mismatch"
    ACCESS_DENIED = "access_denied"
    AUTHORIZATION_FAILED = "authorization_failed"
    INVALID_ID_TOKEN = "invalid_id_token"


class LoginError(BffError):
    """The authorization code flow could not be completed."""

    def __init__(self, code: LoginErrorCode, detail: str) -> None:
        super().__init__(detail)
        self.code = code


class NotAuthenticatedError(BffError):
    """The request has no valid session, or the session can no longer get tokens."""


class CsrfError(BffError):
    """The request may have been sent by another site."""


class UpstreamPathError(BffError):
    """The proxied path tries to leave the allowed resource server."""

    def __init__(self, path: str) -> None:
        super().__init__(f"Path {path!r} is not allowed for the API proxy")


class UpstreamUnavailableError(BffError):
    """The resource server could not be reached."""


class ProviderError(BffError):
    """The authorization server returned something the BFF cannot use."""


class TokenEndpointError(ProviderError):
    """The token endpoint rejected a request with an OAuth error code."""

    def __init__(self, error: str, status_code: int) -> None:
        super().__init__(f"Token endpoint returned {status_code} with error {error!r}")
        self.error = error


class InvalidIdTokenError(BffError):
    """The ID token failed validation."""
