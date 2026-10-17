from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.conftest import BearerFactory

CAMPAIGN_KEYS = {
    "id",
    "name",
    "subject",
    "content",
    "status",
    "sentAt",
    "scheduledFor",
    "createdAt",
    "updatedAt",
    "recipients",
    "stats",
}
RECIPIENT_KEYS = {"id", "clientId", "clientName", "clientEmail", "status", "sentAt", "error"}
STATS_KEYS = {"total", "sent", "failed", "pending", "bounced", "progressPercentage", "successRate"}


async def create_client(
    client: httpx.AsyncClient, bearer: BearerFactory, company_name: str
) -> dict[str, Any]:
    body = {"companyName": company_name, "primaryEmail": f"biuro@{company_name.lower()}.example"}
    response = await client.post("/clients/", json=body, headers=bearer())
    assert response.status_code == 201
    created: dict[str, Any] = response.json()
    return created


async def create(
    client: httpx.AsyncClient, bearer: BearerFactory, name: str = "Jesień", **fields: Any
) -> dict[str, Any]:
    body = {"name": name, "subject": "Nowości", "content": "Dzień dobry"} | fields
    response = await client.post("/campaigns/", json=body, headers=bearer())
    assert response.status_code == 201
    created: dict[str, Any] = response.json()
    return created


async def listed(
    client: httpx.AsyncClient, bearer: BearerFactory, query: str = ""
) -> dict[str, Any]:
    response = await client.get(f"/campaigns/{query}", headers=bearer())
    assert response.status_code == 200
    page: dict[str, Any] = response.json()
    return page


def names(page: dict[str, Any]) -> list[str]:
    return [item["name"] for item in page["items"]]


async def set_status(
    session_factory: async_sessionmaker[AsyncSession], campaign_id: int, status: str
) -> None:
    async with session_factory() as session:
        await session.execute(
            text("UPDATE campaigns SET status = :status WHERE id = :id"),
            {"status": status, "id": campaign_id},
        )
        await session.commit()


CAMPAIGN_BODY = {"name": "Jesień", "subject": "Nowości", "content": "Dzień dobry"}


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        pytest.param("GET", "/campaigns/", None, id="list"),
        pytest.param("POST", "/campaigns/", CAMPAIGN_BODY, id="create"),
        pytest.param("GET", "/campaigns/1", None, id="get"),
        pytest.param("PUT", "/campaigns/1", {"name": "Zima"}, id="update"),
        pytest.param("DELETE", "/campaigns/1", None, id="delete"),
        pytest.param("POST", "/campaigns/1/recipients", [1], id="recipients"),
        pytest.param("POST", "/campaigns/1/send", None, id="send"),
        pytest.param("POST", "/campaigns/1/resend", None, id="resend"),
    ],
)
async def test_missing_token_answers_401(
    client: httpx.AsyncClient, method: str, path: str, body: Any
) -> None:
    response = await client.request(method, path, json=body)

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or missing access token"}
    assert response.headers["www-authenticate"] == 'Bearer realm="demo-api"'


async def test_create_answers_201_with_a_draft_its_recipients_and_stats(
    client: httpx.AsyncClient, bearer: BearerFactory
) -> None:
    acme = await create_client(client, bearer, "Acme")

    response = await client.post(
        "/campaigns/",
        json={
            "name": "  Jesień  ",
            "subject": "Nowości",
            "content": "  Dzień dobry\n",
            "recipientIds": [acme["id"], acme["id"]],
            "scheduledFor": "2026-11-01T09:00:00Z",
        },
        headers=bearer(),
    )

    assert response.status_code == 201
    created = response.json()
    assert set(created) == CAMPAIGN_KEYS
    assert created["name"] == "Jesień"
    assert created["content"] == "  Dzień dobry\n"
    assert created["status"] == "draft"
    assert created["scheduledFor"] == "2026-11-01T09:00:00Z"
    assert created["sentAt"] is None
    [recipient] = created["recipients"]
    assert set(recipient) == RECIPIENT_KEYS
    assert recipient["clientId"] == acme["id"]
    assert recipient["clientName"] == "Acme"
    assert recipient["clientEmail"] == "biuro@acme.example"
    assert recipient["status"] == "pending"
    assert set(created["stats"]) == STATS_KEYS
    assert created["stats"]["total"] == 1
    assert created["stats"]["pending"] == 1


async def test_get_answers_200_with_the_created_campaign(
    client: httpx.AsyncClient, bearer: BearerFactory
) -> None:
    acme = await create_client(client, bearer, "Acme")
    created = await create(client, bearer, recipientIds=[acme["id"]])

    response = await client.get(f"/campaigns/{created['id']}", headers=bearer())

    assert response.status_code == 200
    assert response.json() == created


async def test_list_answers_a_page_newest_first_with_skip_limit_search_and_total(
    client: httpx.AsyncClient, bearer: BearerFactory
) -> None:
    await create(client, bearer, "Alfa")
    await create(client, bearer, "Beta", subject="Rabaty")
    await create(client, bearer, "Gamma")

    everything = await listed(client, bearer)
    first = await listed(client, bearer, "?limit=2")
    second = await listed(client, bearer, "?skip=2&limit=2")
    found = await listed(client, bearer, "?search=RABAT")

    assert set(everything) == {"items", "total"}
    assert (names(everything), everything["total"]) == (["Gamma", "Beta", "Alfa"], 3)
    assert (names(first), first["total"]) == (["Gamma", "Beta"], 3)
    assert (names(second), second["total"]) == (["Alfa"], 3)
    assert (names(found), found["total"]) == (["Beta"], 1)


async def test_update_answers_200_with_a_partial_update(
    client: httpx.AsyncClient, bearer: BearerFactory
) -> None:
    acme = await create_client(client, bearer, "Acme")
    beta = await create_client(client, bearer, "Beta")
    created = await create(
        client, bearer, recipientIds=[acme["id"]], scheduledFor="2026-11-01T09:00:00Z"
    )

    response = await client.put(
        f"/campaigns/{created['id']}",
        json={"name": "Zima", "subject": None, "recipientIds": [beta["id"], acme["id"]]},
        headers=bearer(),
    )

    assert response.status_code == 200
    updated = response.json()
    assert (updated["name"], updated["subject"]) == ("Zima", "Nowości")
    assert updated["scheduledFor"] == "2026-11-01T09:00:00Z"
    assert [r["clientId"] for r in updated["recipients"]] == [acme["id"], beta["id"]]

    cleared = await client.put(
        f"/campaigns/{created['id']}", json={"scheduledFor": None}, headers=bearer()
    )

    assert cleared.status_code == 200
    assert cleared.json()["scheduledFor"] is None


async def test_delete_answers_204_then_the_campaign_is_gone(
    client: httpx.AsyncClient, bearer: BearerFactory
) -> None:
    created = await create(client, bearer)

    response = await client.delete(f"/campaigns/{created['id']}", headers=bearer())

    assert response.status_code == 204
    assert response.content == b""
    not_found = {"detail": f"Campaign {created['id']} not found"}
    fetched = await client.get(f"/campaigns/{created['id']}", headers=bearer())
    assert (fetched.status_code, fetched.json()) == (404, not_found)
    again = await client.delete(f"/campaigns/{created['id']}", headers=bearer())
    assert (again.status_code, again.json()) == (404, not_found)
    assert (await listed(client, bearer))["total"] == 0


async def test_add_recipients_takes_a_bare_array_and_answers_201(
    client: httpx.AsyncClient, bearer: BearerFactory
) -> None:
    acme = await create_client(client, bearer, "Acme")
    beta = await create_client(client, bearer, "Beta")
    created = await create(client, bearer, recipientIds=[acme["id"]])

    response = await client.post(
        f"/campaigns/{created['id']}/recipients",
        json=[acme["id"], beta["id"]],
        headers=bearer(),
    )

    assert response.status_code == 201
    assert set(response.json()) == CAMPAIGN_KEYS
    assert [r["clientName"] for r in response.json()["recipients"]] == ["Acme", "Beta"]


async def test_add_recipients_with_an_object_body_answers_422(
    client: httpx.AsyncClient, bearer: BearerFactory
) -> None:
    acme = await create_client(client, bearer, "Acme")
    created = await create(client, bearer)

    response = await client.post(
        f"/campaigns/{created['id']}/recipients",
        json={"clientIds": [acme["id"]]},
        headers=bearer(),
    )

    assert response.status_code == 422


async def test_unknown_client_ids_answer_400(
    client: httpx.AsyncClient, bearer: BearerFactory
) -> None:
    created = await create(client, bearer)
    unknown = created["id"] + 1000

    on_create = await client.post(
        "/campaigns/", json=CAMPAIGN_BODY | {"recipientIds": [unknown]}, headers=bearer()
    )
    on_update = await client.put(
        f"/campaigns/{created['id']}", json={"recipientIds": [unknown]}, headers=bearer()
    )
    on_add = await client.post(
        f"/campaigns/{created['id']}/recipients", json=[unknown], headers=bearer()
    )

    expected = {"detail": f"Clients not found: {unknown}"}
    for response in (on_create, on_update, on_add):
        assert (response.status_code, response.json()) == (400, expected)


async def test_changing_a_non_draft_answers_400(
    client: httpx.AsyncClient,
    bearer: BearerFactory,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    acme = await create_client(client, bearer, "Acme")
    created = await create(client, bearer)
    await set_status(session_factory, created["id"], "sent")

    updated = await client.put(
        f"/campaigns/{created['id']}", json={"name": "Zima"}, headers=bearer()
    )
    added = await client.post(
        f"/campaigns/{created['id']}/recipients", json=[acme["id"]], headers=bearer()
    )

    assert updated.status_code == 400
    assert updated.json() == {"detail": "Only draft campaigns can be modified"}
    assert added.status_code == 400
    assert added.json() == {"detail": "Only draft campaigns can have recipients added"}


async def test_changing_or_deleting_a_campaign_being_sent_answers_400(
    client: httpx.AsyncClient,
    bearer: BearerFactory,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    acme = await create_client(client, bearer, "Acme")
    created = await create(client, bearer)
    await set_status(session_factory, created["id"], "sending")

    updated = await client.put(
        f"/campaigns/{created['id']}", json={"name": "Zima"}, headers=bearer()
    )
    deleted = await client.delete(f"/campaigns/{created['id']}", headers=bearer())
    added = await client.post(
        f"/campaigns/{created['id']}/recipients", json=[acme["id"]], headers=bearer()
    )

    for response in (updated, deleted):
        assert (response.status_code, response.json()) == (
            400,
            {"detail": "Campaign is being sent"},
        )
    assert added.json() == {"detail": "Only draft campaigns can have recipients added"}
    fetched = await client.get(f"/campaigns/{created['id']}", headers=bearer())
    assert (fetched.json()["name"], fetched.json()["status"]) == ("Jesień", "sending")


@pytest.mark.parametrize(
    ("method", "suffix", "body"),
    [
        pytest.param("GET", "", None, id="get"),
        pytest.param("PUT", "", {"name": "Zima"}, id="update"),
        pytest.param("DELETE", "", None, id="delete"),
        pytest.param("POST", "/recipients", [], id="recipients"),
        pytest.param("POST", "/send", None, id="send"),
        pytest.param("POST", "/resend", None, id="resend"),
    ],
)
async def test_unknown_campaign_answers_404(
    client: httpx.AsyncClient, bearer: BearerFactory, method: str, suffix: str, body: Any
) -> None:
    response = await client.request(
        method, f"/campaigns/999999{suffix}", json=body, headers=bearer()
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Campaign 999999 not found"}


async def test_create_with_an_empty_name_answers_422(
    client: httpx.AsyncClient, bearer: BearerFactory
) -> None:
    response = await client.post(
        "/campaigns/", json=CAMPAIGN_BODY | {"name": "  "}, headers=bearer()
    )

    assert response.status_code == 422
    assert "Campaign name cannot be empty" in response.json()["detail"][0]["msg"]


async def test_list_with_limit_0_answers_422(
    client: httpx.AsyncClient, bearer: BearerFactory
) -> None:
    response = await client.get("/campaigns/?limit=0", headers=bearer())

    assert response.status_code == 422
