import time

import httpx
import pytest

from tests.conftest import BearerFactory, FakeIssuer


async def test_notes_are_created_and_listed_for_the_token_subject(
    client: httpx.AsyncClient, bearer: BearerFactory
) -> None:
    created = await client.post("/notes", json={"text": "Buy milk"}, headers=bearer())

    listed = await client.get("/notes", headers=bearer())

    assert created.status_code == 201
    assert [note["text"] for note in listed.json()] == ["Buy milk"]


async def test_users_see_only_their_own_notes(
    client: httpx.AsyncClient, bearer: BearerFactory
) -> None:
    await client.post("/notes", json={"text": "Alice's note"}, headers=bearer(sub="alice"))

    response = await client.get("/notes", headers=bearer(sub="bob"))

    assert response.json() == []


async def test_missing_token_gets_bearer_challenge(client: httpx.AsyncClient) -> None:
    response = await client.get("/notes")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == 'Bearer realm="demo-api"'


@pytest.mark.parametrize(
    "claims",
    [
        pytest.param({"aud": "demo-bff"}, id="token for another audience"),
        pytest.param({"iss": "https://attacker.test"}, id="foreign issuer"),
        pytest.param({"exp": int(time.time()) - 120}, id="expired"),
        pytest.param({"kid": "unknown-key"}, id="unknown signing key"),
    ],
)
async def test_invalid_tokens_are_rejected(
    client: httpx.AsyncClient, bearer: BearerFactory, claims: dict[str, object]
) -> None:
    response = await client.get("/notes", headers=bearer(**claims))

    assert response.status_code == 401
    assert 'error="invalid_token"' in response.headers["www-authenticate"]


async def test_unsigned_token_is_rejected(client: httpx.AsyncClient) -> None:
    unsigned = "eyJhbGciOiJub25lIiwia2lkIjoidGVzdC1rZXktMSJ9.eyJzdWIiOiJhbGljZSJ9."

    response = await client.get("/notes", headers={"Authorization": f"Bearer {unsigned}"})

    assert response.status_code == 401


async def test_unknown_key_ids_do_not_refetch_jwks_on_every_request(
    client: httpx.AsyncClient, bearer: BearerFactory, issuer: FakeIssuer
) -> None:
    for _ in range(5):
        await client.get("/notes", headers=bearer(kid="random-kid"))

    assert issuer.jwks_requests == 1


async def test_note_text_is_validated(client: httpx.AsyncClient, bearer: BearerFactory) -> None:
    response = await client.post("/notes", json={"text": ""}, headers=bearer())

    assert response.status_code == 422
