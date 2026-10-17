from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.repositories.campaign_repository import CampaignRepository
from app.repositories.client_repository import ClientRepository
from app.repositories.email_repository import EmailRepository
from tests.conftest import BearerFactory

EMAIL_KEYS = {
    "id",
    "campaignId",
    "clientId",
    "recipientEmail",
    "clientName",
    "campaignName",
    "subject",
    "content",
    "status",
    "sentAt",
    "deliveredAt",
    "openedAt",
    "clickedAt",
    "bouncedAt",
    "errorMessage",
    "errorCode",
    "retryCount",
    "maxRetries",
    "smtpMessageId",
    "smtpResponse",
    "createdAt",
    "updatedAt",
}
STATS_KEYS = {
    "total",
    "pending",
    "sending",
    "sent",
    "failed",
    "bounced",
    "rejected",
    "deferred",
    "delivered",
    "opened",
    "clicked",
    "deliveryRate",
    "openRate",
    "clickRate",
    "bounceRate",
}


async def post(client: httpx.AsyncClient, bearer: BearerFactory, path: str, body: Any) -> int:
    response = await client.post(path, json=body, headers=bearer())
    assert response.status_code == 201
    created_id: int = response.json()["id"]
    return created_id


async def add_client(client: httpx.AsyncClient, bearer: BearerFactory, company_name: str) -> int:
    body = {"companyName": company_name, "primaryEmail": f"biuro@{company_name.lower()}.example"}
    return await post(client, bearer, "/clients/", body)


async def add_campaign(client: httpx.AsyncClient, bearer: BearerFactory, name: str) -> int:
    body = {"name": name, "subject": "Nowości", "content": "Dzień dobry"}
    return await post(client, bearer, "/campaigns/", body)


async def add_email(
    session_factory: async_sessionmaker[AsyncSession],
    campaign_id: int,
    client_id: int,
    status: str = "pending",
) -> int:
    """An email created through the repository: nothing in the app writes emails yet."""
    async with session_factory() as session:
        campaign = await CampaignRepository(session).get_by_id(campaign_id)
        recipient = await ClientRepository(session).get_by_id(client_id)
        assert campaign is not None and recipient is not None
        email = await EmailRepository(session).create(
            campaign=campaign,
            client=recipient,
            recipient_email=recipient.primary_email,
            subject="Nowości",
            body="Dzień dobry",
        )
        await session.execute(
            text("UPDATE emails SET status = :status WHERE id = :id"),
            {"status": status, "id": email.id},
        )
        await session.commit()
        return email.id


async def get(client: httpx.AsyncClient, bearer: BearerFactory, path: str) -> Any:
    response = await client.get(path, headers=bearer())
    assert response.status_code == 200
    return response.json()


def ids(items: list[dict[str, Any]]) -> list[int]:
    return [item["id"] for item in items]


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        pytest.param("GET", "/emails/", None, id="list"),
        pytest.param("GET", "/emails/stats/", None, id="stats"),
        pytest.param("GET", "/emails/failed/", None, id="failed"),
        pytest.param("GET", "/emails/campaign/1", None, id="by-campaign"),
        pytest.param("GET", "/emails/client/1", None, id="by-client"),
        pytest.param("GET", "/emails/1", None, id="get"),
        pytest.param("PUT", "/emails/1", {"status": "sent"}, id="update"),
        pytest.param("POST", "/emails/1/mark-opened", None, id="mark-opened"),
        pytest.param("POST", "/emails/1/mark-clicked", None, id="mark-clicked"),
        pytest.param("DELETE", "/emails/1", None, id="delete"),
    ],
)
async def test_missing_token_answers_401(
    client: httpx.AsyncClient, method: str, path: str, body: Any
) -> None:
    response = await client.request(method, path, json=body)

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or missing access token"}
    assert response.headers["www-authenticate"] == 'Bearer realm="demo-api"'


async def test_list_answers_a_page_with_filters_skip_limit_and_total(
    client: httpx.AsyncClient,
    bearer: BearerFactory,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    acme = await add_client(client, bearer, "Acme")
    autumn = await add_campaign(client, bearer, "Jesień")
    winter = await add_campaign(client, bearer, "Zima")
    first = await add_email(session_factory, autumn, acme)
    second = await add_email(session_factory, autumn, acme)
    third = await add_email(session_factory, autumn, acme)
    await add_email(session_factory, winter, acme)

    page = await get(client, bearer, f"/emails/?campaign_id={autumn}&skip=1&limit=1")

    assert set(page) == {"items", "total"}
    assert (ids(page["items"]), page["total"]) == ([second], 3)
    assert set(page["items"][0]) == EMAIL_KEYS
    everything = await get(client, bearer, "/emails/")
    assert everything["total"] == 4
    assert ids(everything["items"])[1:] == [third, second, first]


async def test_list_filters_by_status_has_error_and_search(
    client: httpx.AsyncClient,
    bearer: BearerFactory,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    acme = await add_client(client, bearer, "Acme")
    beta = await add_client(client, bearer, "Beta")
    autumn = await add_campaign(client, bearer, "Jesień")
    failed = await add_email(session_factory, autumn, acme, "failed")
    sent = await add_email(session_factory, autumn, beta, "sent")

    by_status = await get(client, bearer, "/emails/?status=failed")
    by_search = await get(client, bearer, "/emails/?search=beta")
    without_error = await get(client, bearer, "/emails/?has_error=false")

    assert ids(by_status["items"]) == [failed]
    assert ids(by_search["items"]) == [sent]
    assert without_error["total"] == 2


async def test_stats_answers_200_and_is_not_parsed_as_an_email_id(
    client: httpx.AsyncClient,
    bearer: BearerFactory,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    acme = await add_client(client, bearer, "Acme")
    autumn = await add_campaign(client, bearer, "Jesień")
    await add_email(session_factory, autumn, acme, "sent")
    await add_email(session_factory, autumn, acme, "bounced")

    stats = await get(client, bearer, "/emails/stats/")
    by_campaign = await get(client, bearer, f"/emails/stats/?campaign_id={autumn + 1000}")

    assert set(stats) == STATS_KEYS
    assert (stats["total"], stats["sent"], stats["bounced"]) == (2, 1, 1)
    assert (stats["bounceRate"], stats["openRate"]) == (50.0, 0.0)
    assert by_campaign["total"] == 0


async def test_failed_by_campaign_and_by_client_answer_plain_arrays(
    client: httpx.AsyncClient,
    bearer: BearerFactory,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    acme = await add_client(client, bearer, "Acme")
    beta = await add_client(client, bearer, "Beta")
    autumn = await add_campaign(client, bearer, "Jesień")
    winter = await add_campaign(client, bearer, "Zima")
    failed = await add_email(session_factory, autumn, acme, "failed")
    await add_email(session_factory, autumn, beta, "sent")
    winter_email = await add_email(session_factory, winter, beta)

    assert ids(await get(client, bearer, "/emails/failed/")) == [failed]
    assert await get(client, bearer, f"/emails/failed/?campaign_id={winter}") == []
    assert ids(await get(client, bearer, f"/emails/campaign/{winter}")) == [winter_email]
    by_client = await get(client, bearer, f"/emails/client/{beta}?skip=0&limit=1")
    assert ids(by_client) == [winter_email]
    assert set(by_client[0]) == EMAIL_KEYS


async def test_get_answers_the_email_with_the_contract_keys(
    client: httpx.AsyncClient,
    bearer: BearerFactory,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    acme = await add_client(client, bearer, "Acme")
    autumn = await add_campaign(client, bearer, "Jesień")
    email_id = await add_email(session_factory, autumn, acme)

    email = await get(client, bearer, f"/emails/{email_id}")

    assert set(email) == EMAIL_KEYS
    assert email["id"] == email_id
    assert (email["campaignId"], email["clientId"]) == (autumn, acme)
    assert (email["clientName"], email["campaignName"]) == ("Acme", "Jesień")
    assert (email["subject"], email["content"]) == ("Nowości", "Dzień dobry")
    assert email["recipientEmail"] == "biuro@acme.example"
    assert (email["status"], email["retryCount"], email["maxRetries"]) == ("pending", 0, 3)


async def test_update_answers_200_with_the_changed_email(
    client: httpx.AsyncClient,
    bearer: BearerFactory,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    acme = await add_client(client, bearer, "Acme")
    autumn = await add_campaign(client, bearer, "Jesień")
    email_id = await add_email(session_factory, autumn, acme)

    response = await client.put(
        f"/emails/{email_id}",
        json={"status": "failed", "errorMessage": "Mailbox full", "errorCode": "552"},
        headers=bearer(),
    )

    assert response.status_code == 200
    email = response.json()
    assert (email["status"], email["errorMessage"], email["errorCode"]) == (
        "failed",
        "Mailbox full",
        "552",
    )
    assert email["sentAt"] is None


async def test_update_with_an_invalid_status_answers_400(
    client: httpx.AsyncClient,
    bearer: BearerFactory,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    acme = await add_client(client, bearer, "Acme")
    autumn = await add_campaign(client, bearer, "Jesień")
    email_id = await add_email(session_factory, autumn, acme)

    response = await client.put(f"/emails/{email_id}", json={"status": "bogus"}, headers=bearer())

    assert (response.status_code, response.json()) == (
        400,
        {"detail": "Invalid email status: bogus"},
    )


async def test_mark_opened_and_clicked_answer_200_with_the_times_set(
    client: httpx.AsyncClient,
    bearer: BearerFactory,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    acme = await add_client(client, bearer, "Acme")
    autumn = await add_campaign(client, bearer, "Jesień")
    email_id = await add_email(session_factory, autumn, acme, "sent")

    opened = await client.post(f"/emails/{email_id}/mark-opened", headers=bearer())
    clicked = await client.post(f"/emails/{email_id}/mark-clicked", headers=bearer())

    assert (opened.status_code, clicked.status_code) == (200, 200)
    assert opened.json()["openedAt"] is not None
    assert clicked.json()["clickedAt"] is not None
    assert clicked.json()["openedAt"] == opened.json()["openedAt"]
    assert clicked.json()["status"] == "sent"


async def test_delete_answers_the_message_then_404(
    client: httpx.AsyncClient,
    bearer: BearerFactory,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    acme = await add_client(client, bearer, "Acme")
    autumn = await add_campaign(client, bearer, "Jesień")
    email_id = await add_email(session_factory, autumn, acme)
    not_found = {"detail": f"Email {email_id} not found"}

    deleted = await client.delete(f"/emails/{email_id}", headers=bearer())
    fetched = await client.get(f"/emails/{email_id}", headers=bearer())
    again = await client.delete(f"/emails/{email_id}", headers=bearer())

    assert (deleted.status_code, deleted.json()) == (
        200,
        {"message": "Email deleted successfully"},
    )
    assert (fetched.status_code, fetched.json()) == (404, not_found)
    assert (again.status_code, again.json()) == (404, not_found)


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        pytest.param("GET", "/emails/999999", None, id="get"),
        pytest.param("PUT", "/emails/999999", {"status": "sent"}, id="update"),
        pytest.param("POST", "/emails/999999/mark-opened", None, id="mark-opened"),
        pytest.param("POST", "/emails/999999/mark-clicked", None, id="mark-clicked"),
        pytest.param("DELETE", "/emails/999999", None, id="delete"),
    ],
)
async def test_unknown_email_answers_404(
    client: httpx.AsyncClient, bearer: BearerFactory, method: str, path: str, body: Any
) -> None:
    response = await client.request(method, path, json=body, headers=bearer())

    assert (response.status_code, response.json()) == (
        404,
        {"detail": "Email 999999 not found"},
    )


@pytest.mark.parametrize(
    "query",
    ["status=unknown", "has_error=maybe", "limit=0"],
    ids=["status", "has_error", "limit"],
)
async def test_invalid_list_query_answers_422(
    client: httpx.AsyncClient, bearer: BearerFactory, query: str
) -> None:
    response = await client.get(f"/emails/?{query}", headers=bearer())

    assert response.status_code == 422


@pytest.mark.parametrize(
    "path",
    [
        pytest.param("/emails/2147483648", id="email-id-above-int32"),
        pytest.param("/emails/-2147483649", id="email-id-below-int32"),
        pytest.param("/emails/campaign/2147483648", id="by-campaign-id"),
        pytest.param("/emails/client/2147483648", id="by-client-id"),
        pytest.param("/emails/?campaign_id=2147483648", id="list-campaign-id"),
        pytest.param("/emails/?client_id=2147483648", id="list-client-id"),
        pytest.param("/emails/stats/?campaign_id=2147483648", id="stats-campaign-id"),
        pytest.param("/emails/failed/?campaign_id=2147483648", id="failed-campaign-id"),
        pytest.param("/emails/?skip=9223372036854775808", id="skip-above-int64"),
        pytest.param("/emails/?search=a%00b", id="search-nul"),
        pytest.param("/emails/?from_date=0001-01-01T00:00:00%2B05:00", id="from-date-before-utc"),
        pytest.param("/emails/?to_date=9999-12-31T23:59:59-05:00", id="to-date-after-utc"),
    ],
)
async def test_input_past_the_database_limits_answers_422(
    client: httpx.AsyncClient, bearer: BearerFactory, path: str
) -> None:
    response = await client.get(path, headers=bearer())

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("method", "path"),
    [
        pytest.param("PUT", "/emails/2147483648", id="update"),
        pytest.param("POST", "/emails/2147483648/mark-opened", id="mark-opened"),
        pytest.param("POST", "/emails/2147483648/mark-clicked", id="mark-clicked"),
        pytest.param("DELETE", "/emails/2147483648", id="delete"),
    ],
)
async def test_email_id_above_int32_answers_422_on_writes(
    client: httpx.AsyncClient, bearer: BearerFactory, method: str, path: str
) -> None:
    response = await client.request(method, path, json={}, headers=bearer())

    assert response.status_code == 422


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"errorMessage": "a\u0000b"}, id="error-message-nul"),
        pytest.param({"errorCode": "a\u0000b"}, id="error-code-nul"),
        pytest.param({"smtpMessageId": "a\u0000b"}, id="smtp-message-id-nul"),
        pytest.param({"smtpResponse": "a\u0000b"}, id="smtp-response-nul"),
        pytest.param({"sentAt": "0001-01-01T00:00:00+05:00"}, id="sent-at-before-utc"),
        pytest.param({"bouncedAt": "9999-12-31T23:59:59-05:00"}, id="bounced-at-after-utc"),
    ],
)
async def test_update_past_the_database_limits_answers_422_and_writes_nothing(
    client: httpx.AsyncClient,
    bearer: BearerFactory,
    session_factory: async_sessionmaker[AsyncSession],
    body: dict[str, str],
) -> None:
    acme = await add_client(client, bearer, "Acme")
    autumn = await add_campaign(client, bearer, "Jesień")
    email_id = await add_email(session_factory, autumn, acme)
    before = await get(client, bearer, f"/emails/{email_id}")

    response = await client.put(f"/emails/{email_id}", json=body, headers=bearer())

    assert response.status_code == 422
    assert await get(client, bearer, f"/emails/{email_id}") == before


async def test_ids_at_the_int32_limits_answer_404(
    client: httpx.AsyncClient, bearer: BearerFactory
) -> None:
    for email_id in (2147483647, -2147483648):
        response = await client.get(f"/emails/{email_id}", headers=bearer())

        assert (response.status_code, response.json()) == (
            404,
            {"detail": f"Email {email_id} not found"},
        )
