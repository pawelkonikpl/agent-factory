from collections.abc import AsyncIterator
from typing import Any

import aiosmtplib
import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.main import create_app
from app.services.encryption import EncryptionService
from app.services.smtp_config_service import SmtpConfig
from app.services.smtp_sender import LOGIN_WITHOUT_TLS_ERROR, SendResult
from tests.conftest import AUDIENCE, ISSUER, BearerFactory, FakeIssuer, FakeSenders

SETTINGS = {
    "smtpServer": "localhost",
    "smtpPort": 2525,
    "smtpUser": "noreply@localhost",
    "smtpPassword": "any",
    "smtpUseTls": False,
}


@pytest.fixture
def senders() -> FakeSenders:
    return FakeSenders()


@pytest.fixture
async def app(
    issuer: FakeIssuer,
    database_url: str,
    session_factory: async_sessionmaker[AsyncSession],
    senders: FakeSenders,
) -> AsyncIterator[FastAPI]:
    settings = Settings(
        issuer=ISSUER,
        audience=AUDIENCE,
        database_url=database_url,
        encryption_key=EncryptionService.generate_key(),
    )
    async with httpx.AsyncClient(transport=issuer.transport()) as outbound:
        yield create_app(
            settings,
            http_client=outbound,
            session_factory=session_factory,
            email_sender_factory=senders,
        )


async def test_sends_a_test_email_with_the_saved_settings(
    client: httpx.AsyncClient, bearer: BearerFactory, senders: FakeSenders
) -> None:
    await client.put("/config/smtp", json=SETTINGS, headers=bearer())

    response = await client.post(
        "/config/smtp/test", json={"recipient": "jan@example.com"}, headers=bearer()
    )

    assert response.status_code == 200
    assert response.json() == {"success": True, "message": "Test email sent to jan@example.com"}
    assert senders.configs == [
        SmtpConfig(
            smtp_server="localhost",
            smtp_port=2525,
            smtp_user="noreply@localhost",
            smtp_password="any",
            smtp_use_tls=False,
        )
    ]
    [(to, subject, _)] = senders.sent
    assert to == "jan@example.com"
    assert subject == "Email Sender — test połączenia SMTP"


async def test_no_saved_server_answers_400(
    client: httpx.AsyncClient, bearer: BearerFactory, senders: FakeSenders
) -> None:
    response = await client.post(
        "/config/smtp/test", json={"recipient": "jan@example.com"}, headers=bearer()
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "SMTP configuration not found. Please configure SMTP settings first."
    }
    assert senders.sent == []


async def test_settings_of_another_user_are_not_used(
    client: httpx.AsyncClient, bearer: BearerFactory
) -> None:
    await client.put("/config/smtp", json=SETTINGS, headers=bearer(sub="bob"))

    response = await client.post(
        "/config/smtp/test", json={"recipient": "jan@example.com"}, headers=bearer()
    )

    assert response.status_code == 400


async def test_failed_send_answers_400_with_the_error(
    client: httpx.AsyncClient, bearer: BearerFactory, senders: FakeSenders
) -> None:
    senders.result = SendResult(
        success=False, smtp_message_id=None, error="SMTP Authentication failed: (535, 'no')"
    )
    await client.put("/config/smtp", json=SETTINGS, headers=bearer())

    response = await client.post(
        "/config/smtp/test", json={"recipient": "jan@example.com"}, headers=bearer()
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "SMTP Authentication failed: (535, 'no')"}


async def test_login_without_tls_answers_400_without_connecting(
    client: httpx.AsyncClient,
    bearer: BearerFactory,
    senders: FakeSenders,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connections: list[dict[str, Any]] = []
    monkeypatch.setattr(aiosmtplib, "SMTP", lambda **kwargs: connections.append(kwargs))
    senders.real = True
    await client.put("/config/smtp", json=SETTINGS, headers=bearer())

    response = await client.post(
        "/config/smtp/test", json={"recipient": "jan@example.com"}, headers=bearer()
    )

    assert response.status_code == 400
    assert response.json() == {"detail": LOGIN_WITHOUT_TLS_ERROR}
    assert connections == []


async def test_invalid_recipient_answers_422(
    client: httpx.AsyncClient, bearer: BearerFactory, senders: FakeSenders
) -> None:
    await client.put("/config/smtp", json=SETTINGS, headers=bearer())

    response = await client.post(
        "/config/smtp/test", json={"recipient": "not-an-address"}, headers=bearer()
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "recipient"]
    assert senders.sent == []


async def test_missing_token_answers_401(client: httpx.AsyncClient) -> None:
    response = await client.post("/config/smtp/test", json={"recipient": "jan@example.com"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or missing access token"}
