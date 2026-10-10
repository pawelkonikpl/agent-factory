from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from app.config import Settings
from app.services.auth_service import sanitize_return_to
from tests.conftest import CSRF_HEADERS, cookie_attributes, log_in
from tests.fake_authorization_server import FakeAuthorizationServer


def _query(url: str) -> dict[str, str]:
    return {key: values[0] for key, values in parse_qs(urlsplit(url).query).items()}


async def test_login_redirects_to_authorization_endpoint_with_pkce(
    client: httpx.AsyncClient, settings: Settings
) -> None:
    response = await client.get("/bff/login")

    assert response.status_code == 302
    params = _query(response.headers["location"])
    assert params["response_type"] == "code"
    assert params["code_challenge_method"] == "S256"
    assert len(params["code_challenge"]) == 43
    assert params["redirect_uri"] == settings.redirect_uri
    assert params["state"] and params["nonce"]
    assert "code_verifier" not in params


async def test_login_cookie_is_host_prefixed_http_only_and_lax(
    client: httpx.AsyncClient, settings: Settings
) -> None:
    response = await client.get("/bff/login")

    cookie = cookie_attributes(response, settings.login_cookie_name)
    assert settings.login_cookie_name.startswith("__Host-")
    assert "secure" in cookie
    assert "httponly" in cookie
    assert cookie["samesite"].lower() == "lax"
    assert cookie["path"] == "/"
    assert "domain" not in cookie


async def test_callback_creates_session_with_strict_cookie(
    client: httpx.AsyncClient, auth_server: FakeAuthorizationServer, settings: Settings
) -> None:
    response = await log_in(client, auth_server, return_to="/notes")

    assert response.status_code == 303
    assert response.headers["location"] == "/notes"
    cookie = cookie_attributes(response, settings.session_cookie_name)
    assert cookie["samesite"].lower() == "strict"
    assert "httponly" in cookie and "secure" in cookie
    assert "domain" not in cookie


async def test_session_endpoint_returns_user_but_no_tokens(
    client: httpx.AsyncClient, auth_server: FakeAuthorizationServer
) -> None:
    await log_in(client, auth_server)

    response = await client.get("/bff/session", headers=CSRF_HEADERS)

    assert response.status_code == 200
    assert response.json() == {
        "authenticated": True,
        "user": {"sub": "alice", "name": "Alice", "email": "alice@example.com"},
    }
    assert response.headers["cache-control"] == "no-store"
    assert "token" not in response.text


async def test_session_endpoint_reports_anonymous_user(client: httpx.AsyncClient) -> None:
    response = await client.get("/bff/session", headers=CSRF_HEADERS)

    assert response.json() == {"authenticated": False, "user": None}


async def test_callback_rejects_state_mismatch(
    client: httpx.AsyncClient, auth_server: FakeAuthorizationServer, settings: Settings
) -> None:
    login = await client.get("/bff/login")
    callback_url = auth_server.authorize(login.headers["location"])
    tampered = callback_url.replace("state=", "state=x")

    response = await client.get(tampered)

    assert response.headers["location"] == "/?login_error=state_mismatch"
    assert settings.session_cookie_name not in response.headers.get("set-cookie", "")


async def test_callback_rejects_response_from_another_issuer(
    client: httpx.AsyncClient, auth_server: FakeAuthorizationServer
) -> None:
    auth_server.issuer_in_response = "https://attacker.test"

    response = await log_in(client, auth_server)

    assert response.headers["location"] == "/?login_error=issuer_mismatch"


async def test_callback_without_login_cookie_is_rejected(
    client: httpx.AsyncClient, auth_server: FakeAuthorizationServer, settings: Settings
) -> None:
    # An attacker sends the victim a callback URL for a login the victim never started.
    login = await client.get("/bff/login")
    callback_url = auth_server.authorize(login.headers["location"])
    client.cookies.delete(settings.login_cookie_name)

    response = await client.get(callback_url)

    assert response.headers["location"] == "/?login_error=login_expired"


async def test_callback_can_be_used_only_once(
    client: httpx.AsyncClient, auth_server: FakeAuthorizationServer
) -> None:
    login = await client.get("/bff/login")
    callback_url = auth_server.authorize(login.headers["location"])
    await client.get(callback_url)

    replay = await client.get(callback_url)

    assert replay.headers["location"] == "/?login_error=login_expired"


async def test_callback_maps_user_denial_to_access_denied(
    client: httpx.AsyncClient, auth_server: FakeAuthorizationServer
) -> None:
    login = await client.get("/bff/login")
    params = _query(login.headers["location"])

    response = await client.get(
        "/bff/callback",
        params={
            "error": "access_denied",
            "state": params["state"],
            "iss": auth_server.issuer_in_response,
        },
    )

    assert response.headers["location"] == "/?login_error=access_denied"


@pytest.mark.parametrize(
    ("return_to", "expected"),
    [
        ("/notes?tab=1", "/notes?tab=1"),
        ("https://evil.example/", "/"),
        ("//evil.example/", "/"),
        ("/\\evil.example", "/"),
        ("/\t/evil.example", "/"),
        ("javascript:alert(1)", "/"),
        ("", "/"),
        (None, "/"),
    ],
)
def test_sanitize_return_to_allows_only_local_paths(return_to: str | None, expected: str) -> None:
    assert sanitize_return_to(return_to) == expected
