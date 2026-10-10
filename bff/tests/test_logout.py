from urllib.parse import parse_qs, urlsplit

import httpx

from app.config import Settings
from tests.conftest import CSRF_HEADERS, log_in
from tests.fake_authorization_server import FakeAuthorizationServer


async def test_logout_revokes_refresh_token_and_ends_session(
    client: httpx.AsyncClient, auth_server: FakeAuthorizationServer, settings: Settings
) -> None:
    await log_in(client, auth_server)
    refresh_token = next(iter(auth_server.active_refresh_tokens))

    response = await client.post("/bff/logout", headers=CSRF_HEADERS)
    session = await client.get("/bff/session", headers=CSRF_HEADERS)

    assert response.status_code == 200
    assert auth_server.revoked_tokens == [refresh_token]
    assert session.json()["authenticated"] is False
    assert f'{settings.session_cookie_name}=""' in response.headers["set-cookie"]


async def test_logout_returns_rp_initiated_logout_url(
    client: httpx.AsyncClient, auth_server: FakeAuthorizationServer, settings: Settings
) -> None:
    await log_in(client, auth_server)

    response = await client.post("/bff/logout", headers=CSRF_HEADERS)

    logout_url = urlsplit(response.json()["logout_url"])
    params = {key: values[0] for key, values in parse_qs(logout_url.query).items()}
    assert logout_url.path.endswith("/protocol/openid-connect/logout")
    assert params["post_logout_redirect_uri"] == settings.post_logout_redirect_uri
    assert params["client_id"] == settings.client_id
    assert "id_token_hint" in params


async def test_logout_without_session_redirects_to_app(
    client: httpx.AsyncClient, settings: Settings
) -> None:
    response = await client.post("/bff/logout", headers=CSRF_HEADERS)

    assert response.json() == {"logout_url": settings.post_logout_redirect_uri}
