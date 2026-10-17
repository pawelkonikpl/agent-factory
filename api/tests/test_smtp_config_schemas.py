import pytest
from pydantic import ValidationError

from app.schemas.smtp_config import SmtpConfigResponseSchema, SmtpConfigUpdateSchema


@pytest.mark.parametrize("port", [0, 65536])
def test_port_out_of_range_is_rejected(port: int) -> None:
    with pytest.raises(ValidationError):
        SmtpConfigUpdateSchema.model_validate({"smtpPort": port})


@pytest.mark.parametrize("server", ["", "   "], ids=["empty", "whitespace"])
def test_empty_server_is_rejected(server: str) -> None:
    with pytest.raises(ValidationError, match="SMTP server cannot be empty"):
        SmtpConfigUpdateSchema.model_validate({"smtpServer": server})


def test_server_is_trimmed() -> None:
    payload = SmtpConfigUpdateSchema.model_validate({"smtpServer": " smtp.example.com "})

    assert payload.smtp_server == "smtp.example.com"


def test_empty_password_is_rejected() -> None:
    with pytest.raises(ValidationError, match="SMTP password cannot be empty"):
        SmtpConfigUpdateSchema.model_validate({"smtpPassword": ""})


def test_all_fields_null_are_accepted() -> None:
    payload = SmtpConfigUpdateSchema.model_validate(
        {
            "smtpServer": None,
            "smtpPort": None,
            "smtpUser": None,
            "smtpPassword": None,
            "smtpUseTls": None,
        }
    )

    assert payload == SmtpConfigUpdateSchema()


def test_user_that_is_not_an_email_is_accepted() -> None:
    payload = SmtpConfigUpdateSchema.model_validate({"smtpUser": "mailer"})

    assert payload.smtp_user == "mailer"


def test_response_dumps_four_camel_case_fields_without_a_password() -> None:
    response = SmtpConfigResponseSchema(
        smtp_server="smtp.example.com", smtp_port=587, smtp_user="mailer", smtp_use_tls=True
    )

    assert response.model_dump(mode="json", by_alias=True) == {
        "smtpServer": "smtp.example.com",
        "smtpPort": 587,
        "smtpUser": "mailer",
        "smtpUseTls": True,
    }
