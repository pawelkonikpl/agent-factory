from typing import Any

import httpx
import pytest

from tests.conftest import BearerFactory


async def create(client: httpx.AsyncClient, bearer: BearerFactory, name: str) -> dict[str, Any]:
    response = await client.post("/categories/", json={"name": name}, headers=bearer())
    assert response.status_code == 201
    category: dict[str, Any] = response.json()
    return category


async def listed_ids(
    client: httpx.AsyncClient, bearer: BearerFactory, query: str = ""
) -> list[int]:
    response = await client.get(f"/categories/{query}", headers=bearer())
    assert response.status_code == 200
    return [category["id"] for category in response.json()]


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        pytest.param("GET", "/categories/", None, id="list"),
        pytest.param("POST", "/categories/", {"name": "Klienci"}, id="create"),
        pytest.param("PUT", "/categories/1", {"name": "Klienci"}, id="update"),
        pytest.param("DELETE", "/categories/1", None, id="delete"),
    ],
)
async def test_missing_token_answers_401(
    client: httpx.AsyncClient, method: str, path: str, body: dict[str, str] | None
) -> None:
    response = await client.request(method, path, json=body)

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or missing access token"}
    assert response.headers["www-authenticate"] == 'Bearer realm="demo-api"'


async def test_create_answers_201_with_the_trimmed_name_and_is_listed(
    client: httpx.AsyncClient, bearer: BearerFactory
) -> None:
    response = await client.post("/categories/", json={"name": "  Klienci VIP  "}, headers=bearer())

    assert response.status_code == 201
    category = response.json()
    assert set(category) == {"id", "name", "createdAt", "updatedAt"}
    assert category["name"] == "Klienci VIP"
    assert await listed_ids(client, bearer) == [category["id"]]


async def test_categories_are_shared_between_users(
    client: httpx.AsyncClient, bearer: BearerFactory
) -> None:
    category = await create(client, bearer, "Klienci")

    response = await client.get("/categories/", headers=bearer(sub="bob"))

    assert response.status_code == 200
    assert [listed["name"] for listed in response.json()] == ["Klienci"]
    assert response.json()[0]["id"] == category["id"]


async def test_update_answers_200_with_the_new_name(
    client: httpx.AsyncClient, bearer: BearerFactory
) -> None:
    category = await create(client, bearer, "Klienci")

    response = await client.put(
        f"/categories/{category['id']}", json={"name": "Partnerzy"}, headers=bearer()
    )

    assert response.status_code == 200
    assert response.json()["id"] == category["id"]
    assert response.json()["name"] == "Partnerzy"


async def test_delete_answers_204_and_hides_the_category(
    client: httpx.AsyncClient, bearer: BearerFactory
) -> None:
    category = await create(client, bearer, "Klienci")

    response = await client.delete(f"/categories/{category['id']}", headers=bearer())

    assert response.status_code == 204
    assert response.content == b""
    assert await listed_ids(client, bearer) == []


async def test_include_deleted_lists_deleted_categories(
    client: httpx.AsyncClient, bearer: BearerFactory
) -> None:
    kept = await create(client, bearer, "Klienci")
    deleted = await create(client, bearer, "Partnerzy")
    await client.delete(f"/categories/{deleted['id']}", headers=bearer())

    assert await listed_ids(client, bearer, "?include_deleted=true") == [kept["id"], deleted["id"]]


async def test_second_delete_answers_404(client: httpx.AsyncClient, bearer: BearerFactory) -> None:
    category = await create(client, bearer, "Klienci")
    await client.delete(f"/categories/{category['id']}", headers=bearer())

    response = await client.delete(f"/categories/{category['id']}", headers=bearer())

    assert response.status_code == 404
    assert response.json() == {"detail": f"Category {category['id']} not found"}


async def test_create_with_a_taken_name_answers_400(
    client: httpx.AsyncClient, bearer: BearerFactory
) -> None:
    await create(client, bearer, "Klienci")

    response = await client.post("/categories/", json={"name": "Klienci"}, headers=bearer())

    assert response.status_code == 400
    assert response.json() == {"detail": "Category with name 'Klienci' already exists"}


async def test_update_to_a_taken_name_answers_400(
    client: httpx.AsyncClient, bearer: BearerFactory
) -> None:
    await create(client, bearer, "Klienci")
    category = await create(client, bearer, "Partnerzy")

    response = await client.put(
        f"/categories/{category['id']}", json={"name": "Klienci"}, headers=bearer()
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Category with name 'Klienci' already exists"}


async def test_update_of_an_unknown_category_answers_404(
    client: httpx.AsyncClient, bearer: BearerFactory
) -> None:
    response = await client.put("/categories/999999", json={"name": "Klienci"}, headers=bearer())

    assert response.status_code == 404
    assert response.json() == {"detail": "Category 999999 not found"}


async def test_delete_of_an_unknown_category_answers_404(
    client: httpx.AsyncClient, bearer: BearerFactory
) -> None:
    response = await client.delete("/categories/999999", headers=bearer())

    assert response.status_code == 404
    assert response.json() == {"detail": "Category 999999 not found"}


async def test_create_with_an_empty_name_answers_422(
    client: httpx.AsyncClient, bearer: BearerFactory
) -> None:
    response = await client.post("/categories/", json={"name": ""}, headers=bearer())

    assert response.status_code == 422
    assert "Category name cannot be empty" in response.json()["detail"][0]["msg"]


async def test_update_with_a_whitespace_name_answers_422(
    client: httpx.AsyncClient, bearer: BearerFactory
) -> None:
    category = await create(client, bearer, "Klienci")

    response = await client.put(
        f"/categories/{category['id']}", json={"name": "   "}, headers=bearer()
    )

    assert response.status_code == 422
    assert "Category name cannot be empty" in response.json()["detail"][0]["msg"]
