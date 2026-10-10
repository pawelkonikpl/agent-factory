import asyncio

import httpx

from app.config import Settings
from tests.conftest import CSRF_HEADERS, FakeClock, log_in
from tests.fake_authorization_server import ACCESS_TOKEN_LIFETIME, FakeAuthorizationServer


async def test_proxy_sends_access_token_and_keeps_cookies_at_the_bff(
    client: httpx.AsyncClient, auth_server: FakeAuthorizationServer
) -> None:
    await log_in(client, auth_server)

    response = await client.post(
        "/api/notes?sort=desc",
        headers=CSRF_HEADERS | {"Content-Type": "application/json"},
        content=b'{"text": "hi"}',
    )

    upstream = response.json()
    assert response.status_code == 200
    assert upstream["path"] == "/notes"
    assert upstream["query"] == "sort=desc"
    assert upstream["authorization"].startswith("Bearer at-")
    assert upstream["cookie"] is None
    assert upstream["body"] == '{"text": "hi"}'


async def test_proxy_requires_a_session(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/notes", headers=CSRF_HEADERS)

    assert response.status_code == 401


async def test_proxy_rejects_dot_segments(
    client: httpx.AsyncClient, auth_server: FakeAuthorizationServer
) -> None:
    await log_in(client, auth_server)

    response = await client.get("/api/notes/%2e%2e/admin", headers=CSRF_HEADERS)

    assert response.status_code == 400
    assert auth_server.api_requests == []


async def test_proxy_refreshes_expired_access_token(
    client: httpx.AsyncClient, auth_server: FakeAuthorizationServer, clock: FakeClock
) -> None:
    await log_in(client, auth_server)
    first = (await client.get("/api/notes", headers=CSRF_HEADERS)).json()["authorization"]
    clock.advance(ACCESS_TOKEN_LIFETIME)

    second = (await client.get("/api/notes", headers=CSRF_HEADERS)).json()["authorization"]

    assert second != first
    grant_types = [request["grant_type"] for request in auth_server.token_requests]
    assert grant_types == ["authorization_code", "refresh_token"]


async def test_parallel_requests_share_one_refresh(
    client: httpx.AsyncClient, auth_server: FakeAuthorizationServer, clock: FakeClock
) -> None:
    await log_in(client, auth_server)
    clock.advance(ACCESS_TOKEN_LIFETIME)

    responses = await asyncio.gather(
        *(client.get("/api/notes", headers=CSRF_HEADERS) for _ in range(5))
    )

    assert [response.status_code for response in responses] == [200] * 5
    refreshes = [r for r in auth_server.token_requests if r["grant_type"] == "refresh_token"]
    assert len(refreshes) == 1


async def test_rejected_refresh_token_ends_the_session(
    client: httpx.AsyncClient,
    auth_server: FakeAuthorizationServer,
    clock: FakeClock,
    settings: Settings,
) -> None:
    await log_in(client, auth_server)
    auth_server.active_refresh_tokens.clear()  # e.g. revoked by an admin
    clock.advance(ACCESS_TOKEN_LIFETIME)

    response = await client.get("/api/notes", headers=CSRF_HEADERS)
    session = await client.get("/bff/session", headers=CSRF_HEADERS)

    assert response.status_code == 401
    assert settings.session_cookie_name in response.headers["set-cookie"]
    assert session.json()["authenticated"] is False


async def test_session_expires_after_idle_timeout(
    client: httpx.AsyncClient,
    auth_server: FakeAuthorizationServer,
    clock: FakeClock,
    settings: Settings,
) -> None:
    await log_in(client, auth_server)
    clock.advance(settings.session_idle_timeout_seconds + 1)

    response = await client.get("/bff/session", headers=CSRF_HEADERS)

    assert response.json()["authenticated"] is False
