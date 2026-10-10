"""Errors raised by the resource server. HTTP mapping lives in app/main.py."""


class InvalidTokenError(Exception):
    """The request carries no usable access token (RFC 6750 "invalid_token")."""

    def __init__(self, detail: str, *, token_present: bool = True) -> None:
        super().__init__(detail)
        self.token_present = token_present


class KeySetUnavailableError(Exception):
    """The issuer's signing keys could not be loaded."""
