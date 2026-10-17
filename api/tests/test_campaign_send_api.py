from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.main import create_app
from app.services.encryption import EncryptionService
from tests.conftest import AUDIENCE, ISSUER, BearerFactory, FakeIssuer, FakeSenders
from tests.test_campaigns_api import create, create_client, set_status

SETTINGS = {"smtpServer": "localhost", "smtpPort": 2525, "smtpUseTls": False}


@pytest.fixture
def senders() -> FakeSenders:
    return FakeSenders()


@pytest.fixture
def email_max_concurrent() -> int:
    """The API_EMAIL_MAX_CONCURRENT setting; a test parametrizes it to change it."""
    return 10


@pytest.fixture
async def app(
    issuer: FakeIssuer,
    database_url: str,
    session_factory: async_sessionmaker[AsyncSession],
    senders: FakeSenders,
    email_max_concurrent: int,
) -> AsyncIterator[FastAPI]:
    settings = Settings(
        issuer=ISSUER,
        audience=AUDIENCE,
        database_url=database_url,
        encryption_key=EncryptionService.generate_key(),
        email_max_concurrent=email_max_concurrent,
    )
    async with httpx.AsyncClient(transport=issuer.transport()) as outbound:
        yield create_app(
            settings,
            http_client=outbound,
            session_factory=session_factory,
            email_sender_factory=senders,
        )


async def draft_with_recipients(
    client: httpx.AsyncClient, bearer: BearerFactory, names: list[str], **fields: Any
) -> dict[str, Any]:
    ids = [(await create_client(client, bearer, name))["id"] for name in names]
    return await create(client, bearer, recipientIds=ids, **fields)


async def get(client: httpx.AsyncClient, bearer: BearerFactory, campaign_id: int) -> Any:
    response = await client.get(f"/campaigns/{campaign_id}", headers=bearer())
    assert response.status_code == 200
    return response.json()


async def emails(client: httpx.AsyncClient, bearer: BearerFactory, campaign_id: int) -> Any:
    response = await client.get(f"/emails/campaign/{campaign_id}", headers=bearer())
    assert response.status_code == 200
    return response.json()


async def send(
    client: httpx.AsyncClient, bearer: BearerFactory, campaign_id: int, query: str = ""
) -> httpx.Response:
    return await client.post(f"/campaigns/{campaign_id}/send{query}", headers=bearer())


def by_email(items: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    return {item[key]: item for item in items}


async def test_send_answers_202_then_sends_to_every_recipient(
    client: httpx.AsyncClient, bearer: BearerFactory, senders: FakeSenders
) -> None:
    await client.put("/config/smtp", json=SETTINGS, headers=bearer())
    created = await draft_with_recipients(
        client, bearer, ["Acme", "Beta", "Gamma"], content="Dzień dobry {name},\n{email}"
    )

    response = await send(client, bearer, created["id"])

    assert response.status_code == 202
    assert response.json()["status"] == "sending"
    campaign = await get(client, bearer, created["id"])
    assert campaign["status"] == "sent"
    assert campaign["sentAt"] is not None
    assert {recipient["status"] for recipient in campaign["recipients"]} == {"sent"}
    assert campaign["stats"]["sent"] == 3
    logged = await emails(client, bearer, created["id"])
    assert len(logged) == 3
    for email in logged:
        address = email["recipientEmail"]
        name = address.removeprefix("biuro@").removesuffix(".example").capitalize()
        assert email["status"] == "sent"
        assert email["smtpMessageId"] == "<1@test>"
        assert email["subject"] == "Nowości"
        assert email["content"] == f"Dzień dobry {name},<br>{address}"
    assert sorted(to for to, _, _ in senders.sent) == sorted(e["recipientEmail"] for e in logged)


async def test_one_failure_fails_the_campaign_and_resending_retries_only_it(
    client: httpx.AsyncClient, bearer: BearerFactory, senders: FakeSenders
) -> None:
    await client.put("/config/smtp", json=SETTINGS, headers=bearer())
    created = await draft_with_recipients(client, bearer, ["Acme", "Beta", "Gamma"])
    senders.failures = {"biuro@beta.example": "Recipient refused: no such user"}

    await send(client, bearer, created["id"])

    campaign = await get(client, bearer, created["id"])
    assert campaign["status"] == "failed"
    assert (campaign["stats"]["sent"], campaign["stats"]["failed"]) == (2, 1)
    beta = by_email(campaign["recipients"], "clientEmail")["biuro@beta.example"]
    assert (beta["status"], beta["error"]) == ("failed", "Recipient refused: no such user")
    logged = by_email(await emails(client, bearer, created["id"]), "recipientEmail")
    failed = logged["biuro@beta.example"]
    assert (failed["status"], failed["errorMessage"], failed["retryCount"]) == (
        "failed",
        "Recipient refused: no such user",
        0,
    )

    senders.failures = {}
    senders.sent.clear()
    response = await send(client, bearer, created["id"])

    assert response.status_code == 202
    assert [to for to, _, _ in senders.sent] == ["biuro@beta.example"]
    campaign = await get(client, bearer, created["id"])
    assert campaign["status"] == "sent"
    assert {recipient["status"] for recipient in campaign["recipients"]} == {"sent"}
    logged = by_email(await emails(client, bearer, created["id"]), "recipientEmail")
    assert len(logged) == 3
    retried = logged["biuro@beta.example"]
    assert (retried["id"], retried["status"], retried["retryCount"]) == (failed["id"], "sent", 1)
    assert retried["errorMessage"] is None


@pytest.mark.parametrize(
    ("status", "names", "smtp", "detail"),
    [
        pytest.param(
            "sent",
            ["Acme"],
            True,
            "Campaign cannot be sent — current status: sent",
            id="sent",
        ),
        pytest.param(
            "sending",
            ["Acme"],
            True,
            "Campaign cannot be sent — current status: sending",
            id="sending",
        ),
        pytest.param("draft", [], True, "Campaign has no pending recipients", id="no-recipients"),
        pytest.param(
            "draft",
            ["Acme"],
            False,
            "SMTP configuration not found. Please configure SMTP settings first.",
            id="no-smtp",
        ),
    ],
)
async def test_a_failing_check_answers_400_and_changes_nothing(
    client: httpx.AsyncClient,
    bearer: BearerFactory,
    session_factory: async_sessionmaker[AsyncSession],
    senders: FakeSenders,
    status: str,
    names: list[str],
    smtp: bool,
    detail: str,
) -> None:
    if smtp:
        await client.put("/config/smtp", json=SETTINGS, headers=bearer())
    created = await draft_with_recipients(client, bearer, names)
    await set_status(session_factory, created["id"], status)
    before = await get(client, bearer, created["id"])

    response = await send(client, bearer, created["id"])

    assert (response.status_code, response.json()) == (400, {"detail": detail})
    assert await get(client, bearer, created["id"]) == before
    assert senders.configs == []
    assert senders.sent == []


async def test_a_failed_campaign_with_no_failed_recipients_answers_400(
    client: httpx.AsyncClient,
    bearer: BearerFactory,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.put("/config/smtp", json=SETTINGS, headers=bearer())
    created = await draft_with_recipients(client, bearer, ["Acme"])
    await set_status(session_factory, created["id"], "failed")

    response = await send(client, bearer, created["id"])

    assert response.status_code == 400
    assert response.json() == {"detail": "Campaign has no pending recipients"}


async def test_an_unknown_or_deleted_campaign_answers_404(
    client: httpx.AsyncClient, bearer: BearerFactory, senders: FakeSenders
) -> None:
    await client.put("/config/smtp", json=SETTINGS, headers=bearer())
    created = await draft_with_recipients(client, bearer, ["Acme"])
    await client.delete(f"/campaigns/{created['id']}", headers=bearer())

    unknown = await send(client, bearer, 999999)
    deleted = await send(client, bearer, created["id"])

    assert (unknown.status_code, unknown.json()) == (
        404,
        {"detail": "Campaign 999999 not found"},
    )
    assert (deleted.status_code, deleted.json()) == (
        404,
        {"detail": f"Campaign {created['id']} not found"},
    )
    assert senders.sent == []


@pytest.mark.parametrize("max_concurrent", [0, 51])
async def test_max_concurrent_out_of_range_answers_422(
    client: httpx.AsyncClient, bearer: BearerFactory, senders: FakeSenders, max_concurrent: int
) -> None:
    await client.put("/config/smtp", json=SETTINGS, headers=bearer())
    created = await draft_with_recipients(client, bearer, ["Acme"])

    response = await send(client, bearer, created["id"], f"?max_concurrent={max_concurrent}")

    assert response.status_code == 422
    assert (await get(client, bearer, created["id"]))["status"] == "draft"
    assert senders.sent == []


async def test_max_concurrent_limits_the_sends_in_flight(
    client: httpx.AsyncClient, bearer: BearerFactory, senders: FakeSenders
) -> None:
    await client.put("/config/smtp", json=SETTINGS, headers=bearer())
    created = await draft_with_recipients(client, bearer, [f"Firma{n}" for n in range(6)])

    response = await send(client, bearer, created["id"], "?max_concurrent=2")

    assert response.status_code == 202
    assert len(senders.sent) == 6
    assert senders.max_in_flight == 2


@pytest.mark.parametrize("email_max_concurrent", [3])
async def test_without_max_concurrent_the_setting_is_used(
    client: httpx.AsyncClient, bearer: BearerFactory, senders: FakeSenders
) -> None:
    await client.put("/config/smtp", json=SETTINGS, headers=bearer())
    created = await draft_with_recipients(client, bearer, [f"Firma{n}" for n in range(6)])

    response = await send(client, bearer, created["id"])

    assert response.status_code == 202
    assert len(senders.sent) == 6
    assert senders.max_in_flight == 3
