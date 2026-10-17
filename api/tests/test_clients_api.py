from typing import Any

import httpx
import pytest

from tests.conftest import BearerFactory

CLIENT_KEYS = {
    "id",
    "companyName",
    "primaryEmail",
    "additionalEmails",
    "phoneNumber",
    "address",
    "isActive",
    "notes",
    "createdAt",
    "updatedAt",
    "categories",
}


async def create(
    client: httpx.AsyncClient,
    bearer: BearerFactory,
    company_name: str,
    primary_email: str,
    **fields: Any,
) -> dict[str, Any]:
    body = {"companyName": company_name, "primaryEmail": primary_email} | fields
    response = await client.post("/clients/", json=body, headers=bearer())
    assert response.status_code == 201
    created: dict[str, Any] = response.json()
    return created


async def create_category(
    client: httpx.AsyncClient, bearer: BearerFactory, name: str
) -> dict[str, Any]:
    response = await client.post("/categories/", json={"name": name}, headers=bearer())
    assert response.status_code == 201
    category: dict[str, Any] = response.json()
    return category


async def listed(
    client: httpx.AsyncClient, bearer: BearerFactory, query: str = ""
) -> dict[str, Any]:
    response = await client.get(f"/clients/{query}", headers=bearer())
    assert response.status_code == 200
    page: dict[str, Any] = response.json()
    return page


def names(page: dict[str, Any]) -> list[str]:
    return [item["companyName"] for item in page["items"]]


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        pytest.param("GET", "/clients/", None, id="list"),
        pytest.param(
            "POST",
            "/clients/",
            {"companyName": "Acme", "primaryEmail": "biuro@acme.example"},
            id="create",
        ),
        pytest.param("GET", "/clients/1", None, id="get"),
        pytest.param(
            "PUT",
            "/clients/1",
            {"companyName": "Acme", "primaryEmail": "biuro@acme.example"},
            id="update",
        ),
        pytest.param("DELETE", "/clients/1", None, id="delete"),
    ],
)
async def test_missing_token_answers_401(
    client: httpx.AsyncClient, method: str, path: str, body: dict[str, str] | None
) -> None:
    response = await client.request(method, path, json=body)

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or missing access token"}
    assert response.headers["www-authenticate"] == 'Bearer realm="demo-api"'


async def test_create_answers_201_and_get_answers_200_with_the_same_client(
    client: httpx.AsyncClient, bearer: BearerFactory
) -> None:
    category = await create_category(client, bearer, "Hurtownie")

    response = await client.post(
        "/clients/",
        json={
            "companyName": "  Acme Sp. z o.o.  ",
            "primaryEmail": "biuro@acme.example",
            "categoryIds": [category["id"]],
        },
        headers=bearer(),
    )

    assert response.status_code == 201
    created = response.json()
    assert set(created) == CLIENT_KEYS
    assert created["companyName"] == "Acme Sp. z o.o."
    assert created["categories"] == [category]
    fetched = await client.get(f"/clients/{created['id']}", headers=bearer())
    assert fetched.status_code == 200
    assert fetched.json() == created


async def test_list_answers_a_page_with_skip_limit_search_and_total(
    client: httpx.AsyncClient, bearer: BearerFactory
) -> None:
    await create(client, bearer, "Gamma", "biuro@gamma.example")
    await create(client, bearer, "Alfa", "biuro@alfa.example")
    await create(client, bearer, "Beta", "biuro@beta.example")

    first = await listed(client, bearer, "?limit=2")
    second = await listed(client, bearer, "?skip=2&limit=2")
    found = await listed(client, bearer, "?search=GAMM")

    assert set(first) == {"items", "total"}
    assert (names(first), first["total"]) == (["Alfa", "Beta"], 3)
    assert (names(second), second["total"]) == (["Gamma"], 3)
    assert (names(found), found["total"]) == (["Gamma"], 1)


async def test_clients_are_shared_between_users(
    client: httpx.AsyncClient, bearer: BearerFactory
) -> None:
    created = await create(client, bearer, "Acme", "biuro@acme.example")

    response = await client.get("/clients/", headers=bearer(sub="bob"))

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [created["id"]]


async def test_update_is_a_full_replacement(
    client: httpx.AsyncClient, bearer: BearerFactory
) -> None:
    category = await create_category(client, bearer, "Hurtownie")
    created = await create(
        client,
        bearer,
        "Acme",
        "biuro@acme.example",
        additionalEmails="handel@acme.example",
        phoneNumber="+48 600 100 200",
        address="ul. Prosta 1, Warszawa",
        isActive=False,
        notes="Stały klient",
        categoryIds=[category["id"]],
    )

    response = await client.put(
        f"/clients/{created['id']}",
        json={"companyName": "Acme Sp. z o.o.", "primaryEmail": "biuro@acme.example"},
        headers=bearer(),
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["id"] == created["id"]
    assert updated["companyName"] == "Acme Sp. z o.o."
    assert updated["additionalEmails"] is None
    assert updated["phoneNumber"] is None
    assert updated["address"] is None
    assert updated["notes"] is None
    assert updated["isActive"] is True
    assert updated["categories"] == []


async def test_delete_answers_204_and_the_client_is_gone(
    client: httpx.AsyncClient, bearer: BearerFactory
) -> None:
    created = await create(client, bearer, "Acme", "biuro@acme.example")

    response = await client.delete(f"/clients/{created['id']}", headers=bearer())

    assert response.status_code == 204
    assert response.content == b""
    assert await listed(client, bearer) == {"items": [], "total": 0}
    fetched = await client.get(f"/clients/{created['id']}", headers=bearer())
    assert fetched.status_code == 404
    assert fetched.json() == {"detail": f"Client {created['id']} not found"}
    second = await client.delete(f"/clients/{created['id']}", headers=bearer())
    assert second.status_code == 404
    assert second.json() == {"detail": f"Client {created['id']} not found"}


async def test_create_with_a_taken_email_answers_400(
    client: httpx.AsyncClient, bearer: BearerFactory
) -> None:
    await create(client, bearer, "Acme", "biuro@acme.example")

    response = await client.post(
        "/clients/",
        json={"companyName": "Acme Bis", "primaryEmail": "biuro@acme.example"},
        headers=bearer(),
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Client with email 'biuro@acme.example' already exists"}


async def test_update_to_a_taken_email_answers_400(
    client: httpx.AsyncClient, bearer: BearerFactory
) -> None:
    await create(client, bearer, "Acme", "biuro@acme.example")
    created = await create(client, bearer, "Beta", "biuro@beta.example")

    response = await client.put(
        f"/clients/{created['id']}",
        json={"companyName": "Beta", "primaryEmail": "biuro@acme.example"},
        headers=bearer(),
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Client with email 'biuro@acme.example' already exists"}


async def test_create_with_an_unknown_category_answers_400(
    client: httpx.AsyncClient, bearer: BearerFactory
) -> None:
    response = await client.post(
        "/clients/",
        json={
            "companyName": "Acme",
            "primaryEmail": "biuro@acme.example",
            "categoryIds": [999999],
        },
        headers=bearer(),
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Categories not found: 999999"}


@pytest.mark.parametrize(
    ("method", "body"),
    [
        pytest.param("GET", None, id="get"),
        pytest.param(
            "PUT", {"companyName": "Acme", "primaryEmail": "biuro@acme.example"}, id="update"
        ),
        pytest.param("DELETE", None, id="delete"),
    ],
)
async def test_unknown_client_answers_404(
    client: httpx.AsyncClient, bearer: BearerFactory, method: str, body: dict[str, str] | None
) -> None:
    response = await client.request(method, "/clients/999999", json=body, headers=bearer())

    assert response.status_code == 404
    assert response.json() == {"detail": "Client 999999 not found"}


async def test_create_with_an_empty_company_name_answers_422(
    client: httpx.AsyncClient, bearer: BearerFactory
) -> None:
    response = await client.post(
        "/clients/",
        json={"companyName": "", "primaryEmail": "biuro@acme.example"},
        headers=bearer(),
    )

    assert response.status_code == 422
    assert "Company name cannot be empty" in response.json()["detail"][0]["msg"]


async def test_create_with_an_invalid_email_answers_422(
    client: httpx.AsyncClient, bearer: BearerFactory
) -> None:
    response = await client.post(
        "/clients/", json={"companyName": "Acme", "primaryEmail": "not-an-email"}, headers=bearer()
    )

    assert response.status_code == 422
    assert [problem["loc"] for problem in response.json()["detail"]] == [["body", "primaryEmail"]]


async def test_list_with_limit_0_answers_422(
    client: httpx.AsyncClient, bearer: BearerFactory
) -> None:
    response = await client.get("/clients/?limit=0", headers=bearer())

    assert response.status_code == 422
    assert [problem["loc"] for problem in response.json()["detail"]] == [["query", "limit"]]


async def test_deleting_a_category_removes_it_from_its_clients(
    client: httpx.AsyncClient, bearer: BearerFactory
) -> None:
    deleted = await create_category(client, bearer, "Hurtownie")
    kept = await create_category(client, bearer, "Detal")
    created = await create(
        client,
        bearer,
        "Acme",
        "biuro@acme.example",
        categoryIds=[deleted["id"], kept["id"]],
    )

    response = await client.delete(f"/categories/{deleted['id']}", headers=bearer())

    assert response.status_code == 204
    fetched = await client.get(f"/clients/{created['id']}", headers=bearer())
    assert fetched.status_code == 200
    assert fetched.json()["categories"] == [kept]
