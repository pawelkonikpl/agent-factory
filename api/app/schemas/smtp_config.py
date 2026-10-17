"""SMTP settings schemas (api-contract.md §2). The password is write-only."""

from typing import Annotated

from pydantic import AfterValidator, Field

from app.schemas.base import BaseSchema


def validate_smtp_server(value: str) -> str:
    server = value.strip()
    if not server:
        raise ValueError("SMTP server cannot be empty")
    return server


def validate_smtp_user(value: str) -> str:
    # Any login, not necessarily an email address.
    user = value.strip()
    if not user:
        raise ValueError("SMTP user cannot be empty")
    return user


def validate_smtp_password(value: str) -> str:
    # Not trimmed: spaces can be part of a password.
    if not value:
        raise ValueError("SMTP password cannot be empty")
    return value


class SmtpConfigResponseSchema(BaseSchema):
    smtp_server: str | None
    smtp_port: int | None
    smtp_user: str | None
    smtp_use_tls: bool | None


class SmtpConfigUpdateSchema(BaseSchema):
    """None (omitted or null) leaves the stored value unchanged; a field can't be cleared."""

    smtp_server: Annotated[str, AfterValidator(validate_smtp_server)] | None = None
    smtp_port: Annotated[int, Field(ge=1, le=65535)] | None = None
    smtp_user: Annotated[str, AfterValidator(validate_smtp_user)] | None = None
    smtp_password: Annotated[str, AfterValidator(validate_smtp_password)] | None = None
    smtp_use_tls: bool | None = None
