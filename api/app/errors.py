"""Errors raised by the resource server. HTTP mapping lives in app/main.py."""


class InvalidTokenError(Exception):
    """The request carries no usable access token (RFC 6750 "invalid_token")."""

    def __init__(self, detail: str, *, token_present: bool = True) -> None:
        super().__init__(detail)
        self.token_present = token_present


class KeySetUnavailableError(Exception):
    """The issuer's signing keys could not be loaded."""


class DomainError(Exception):
    """Base of the errors a service raises when it rejects a request; raise a subclass."""


class NotFoundError(DomainError):
    """Raise when the requested resource does not exist."""


class ConflictError(DomainError):
    """Raise when the change clashes with existing data, such as a duplicate name."""


class BusinessRuleError(DomainError):
    """Raise when the request breaks a business rule, such as editing a sent campaign."""
