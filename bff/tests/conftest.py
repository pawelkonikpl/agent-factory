import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import httpx
import pytest
from pydantic import SecretStr

from app.config import Settings
from app.main import create_app
from tests.fake_authorization_server import (
    API_BASE_URL,
    CLIENT_ID,
    CLIENT_SECRET,
    ISSUER,
    REDIRECT_URI,
    FakeAuthorizationServer,
)

APP_ORIGIN = "https://app.test"
CSRF_HEADERS = {"X-CSRF": "1"}


@dataclass
class FakeClock:
    # Starts at real time: PyJWT checks iat and exp against the system clock.
    now: float = field(default_factory=time.time)

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def settings() -> Settings:
    return Settings(
        issuer=ISSUER,
        client_id=CLIENT_ID,
        client_secret=SecretStr(CLIENT_SECRET),
        redirect_uri=REDIRECT_URI,
        post_logout_redirect_uri=f"{APP_ORIGIN}/",
        app_origin=APP_ORIGIN,
        api_base_url=API_BASE_URL,
        cookie_secure=True,
    )


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def auth_server(clock: FakeClock) -> FakeAuthorizationServer:
    return FakeAuthorizationServer(clock=clock)


@pytest.fixture
async def client(
    settings: Settings, auth_server: FakeAuthorizationServer, clock: FakeClock
) -> AsyncIterator[httpx.AsyncClient]:
    """A browser talking to the BFF on the app's origin."""
    async with httpx.AsyncClient(transport=auth_server.transport()) as outbound:
        app = create_app(settings, http_client=outbound, clock=clock)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=APP_ORIGIN
        ) as browser:
            yield browser


async def log_in(
    browser: httpx.AsyncClient, auth_server: FakeAuthorizationServer, return_to: str = "/"
) -> httpx.Response:
    """Runs the whole login and returns the BFF's response to the callback."""
    login = await browser.get("/bff/login", params={"returnTo": return_to})
    callback_url = auth_server.authorize(login.headers["location"])
    return await browser.get(_path_and_query(callback_url))


def _path_and_query(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.path}?{parts.query}"


def cookie_attributes(response: httpx.Response, name: str) -> dict[str, str]:
    """Parses the Set-Cookie header for one cookie into {attribute: value}."""
    for header in response.headers.get_list("set-cookie"):
        first, *attributes = [part.strip() for part in header.split(";")]
        cookie_name, _, value = first.partition("=")
        if cookie_name == name:
            parsed = {"value": value.strip('"')}
            for attribute in attributes:
                key, _, attribute_value = attribute.partition("=")
                parsed[key.lower()] = attribute_value
            return parsed
    raise AssertionError(f"No Set-Cookie header for {name}")
