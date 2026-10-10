import httpx
import pytest

from tests.conftest import APP_ORIGIN, CSRF_HEADERS, log_in
from tests.fake_authorization_server import FakeAuthorizationServer


@pytest.mark.parametrize(
    ("method", "path"),
    [("GET", "/bff/session"), ("POST", "/bff/logout"), ("GET", "/api/notes")],
)
async def test_requests_without_csrf_header_are_rejected(
    client: httpx.AsyncClient, auth_server: FakeAuthorizationServer, method: str, path: str
) -> None:
    await log_in(client, auth_server)

    response = await client.request(method, path)

    assert response.status_code == 403


async def test_request_from_foreign_origin_is_rejected(
    client: httpx.AsyncClient, auth_server: FakeAuthorizationServer
) -> None:
    await log_in(client, auth_server)

    response = await client.post(
        "/api/notes", headers=CSRF_HEADERS | {"Origin": "https://evil.example"}
    )

    assert response.status_code == 403


async def test_cross_site_fetch_metadata_is_rejected(
    client: httpx.AsyncClient, auth_server: FakeAuthorizationServer
) -> None:
    await log_in(client, auth_server)

    response = await client.get(
        "/api/notes", headers=CSRF_HEADERS | {"Sec-Fetch-Site": "cross-site"}
    )

    assert response.status_code == 403


async def test_same_origin_request_passes(
    client: httpx.AsyncClient, auth_server: FakeAuthorizationServer
) -> None:
    await log_in(client, auth_server)

    response = await client.post(
        "/api/notes",
        headers=CSRF_HEADERS | {"Origin": APP_ORIGIN, "Sec-Fetch-Site": "same-origin"},
    )

    assert response.status_code == 200
