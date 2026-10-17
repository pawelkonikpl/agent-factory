import httpx
import pytest

from tests.conftest import BearerFactory

EMPTY = {"smtpServer": None, "smtpPort": None, "smtpUser": None, "smtpUseTls": None}


@pytest.mark.parametrize("method", ["GET", "PUT"])
async def test_missing_token_answers_401(client: httpx.AsyncClient, method: str) -> None:
    response = await client.request(method, "/config/smtp", json={"smtpPort": 587})

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or missing access token"}


async def test_get_answers_all_null_before_saving(
    client: httpx.AsyncClient, bearer: BearerFactory
) -> None:
    response = await client.get("/config/smtp", headers=bearer())

    assert response.status_code == 200
    assert response.json() == EMPTY


async def test_put_saves_and_get_returns_the_values_without_a_password(
    client: httpx.AsyncClient, bearer: BearerFactory
) -> None:
    body = {
        "smtpServer": " smtp.example.com ",
        "smtpPort": 587,
        "smtpUser": "noreply@localhost",
        "smtpPassword": "secret",
        "smtpUseTls": False,
    }

    response = await client.put("/config/smtp", json=body, headers=bearer())

    assert response.status_code == 200
    assert response.json() == {"message": "Configuration updated successfully"}
    saved = await client.get("/config/smtp", headers=bearer())
    assert saved.json() == {
        "smtpServer": "smtp.example.com",
        "smtpPort": 587,
        "smtpUser": "noreply@localhost",
        "smtpUseTls": False,
    }


async def test_put_answers_422_for_port_0(client: httpx.AsyncClient, bearer: BearerFactory) -> None:
    response = await client.put("/config/smtp", json={"smtpPort": 0}, headers=bearer())

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "smtpPort"]


async def test_settings_saved_by_alice_are_not_seen_by_bob(
    client: httpx.AsyncClient, bearer: BearerFactory
) -> None:
    await client.put("/config/smtp", json={"smtpServer": "smtp.alice.test"}, headers=bearer())

    response = await client.get("/config/smtp", headers=bearer(sub="bob"))

    assert response.status_code == 200
    assert response.json() == EMPTY
