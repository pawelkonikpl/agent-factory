import asyncio
import json
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import Settings
from app.database import run_migrations
from app.main import create_app

ISSUER = "https://idp.test/realms/demo"
AUDIENCE = "demo-api"
KEY_ID = "test-key-1"
TEST_DATABASE = "emailsender_test"


def resolve_test_database_url(settings: Settings | None = None) -> str:
    """API_TEST_DATABASE_URL, else API_DATABASE_URL with the database named emailsender_test."""
    settings = settings or Settings()
    if settings.test_database_url:
        url = make_url(settings.test_database_url)
    else:
        url = make_url(settings.database_url).set(database=TEST_DATABASE)
    return check_test_database(url)


def check_test_database(url: URL) -> str:
    """Refuse any database whose name lacks "test": the fixtures drop its schema."""
    if "test" not in (url.database or ""):
        raise RuntimeError(f"Refusing to run tests against non-test database {url.database!r}")
    return url.render_as_string(hide_password=False)


async def _prepare_database(url: URL) -> None:
    """Create the test database when missing, then give it an empty public schema."""
    # CREATE DATABASE cannot run in a transaction: use autocommit.
    server = create_async_engine(
        url.set(database="postgres"), poolclass=NullPool, isolation_level="AUTOCOMMIT"
    )
    try:
        async with server.connect() as connection:
            exists = await connection.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database}
            )
            if not exists:
                await connection.execute(text(f'CREATE DATABASE "{url.database}"'))
    finally:
        await server.dispose()

    database = create_async_engine(url, poolclass=NullPool)
    try:
        async with database.begin() as connection:
            await connection.execute(text("DROP SCHEMA public CASCADE"))
            await connection.execute(text("CREATE SCHEMA public"))
    finally:
        await database.dispose()


async def _server_answers(url: URL) -> bool:
    engine = create_async_engine(url.set(database="postgres"), poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except (OSError, TimeoutError):
        return False
    finally:
        await engine.dispose()
    return True


@pytest.fixture(scope="session", autouse=True)
def database_url() -> str:
    """The migrated test database, reset once per run. Synchronous: env.py calls asyncio.run."""
    url = resolve_test_database_url()
    parsed = make_url(url)
    if not asyncio.run(_server_answers(parsed)):
        pytest.fail(
            f"PostgreSQL is not reachable at {parsed.host}:{parsed.port} "
            "(API_TEST_DATABASE_URL). Start it with make docker-up.",
            pytrace=False,
        )
    asyncio.run(_prepare_database(parsed))
    run_migrations(url)
    return url


@pytest.fixture
async def session_factory(database_url: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Sessions inside one outer transaction, rolled back after the test (W-25).

    The engine is per test: asyncpg connections belong to the test's event loop.
    """
    engine = create_async_engine(database_url, poolclass=NullPool)
    connection = await engine.connect()
    transaction = await connection.begin()
    try:
        yield async_sessionmaker(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
    finally:
        await transaction.rollback()
        await connection.close()
        await engine.dispose()


@dataclass
class FakeIssuer:
    """Serves discovery and JWKS, and signs access tokens like the authorization server."""

    private_key: rsa.RSAPrivateKey = field(
        default_factory=lambda: rsa.generate_private_key(public_exponent=65537, key_size=2048)
    )
    jwks_requests: int = 0

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def token(self, *, kid: str = KEY_ID, **claim_overrides: Any) -> str:
        now = int(time.time())
        claims = {
            "iss": ISSUER,
            "sub": "alice",
            # Keycloak adds "account" by default; the audience mapper adds "demo-api".
            "aud": [AUDIENCE, "account"],
            "azp": "demo-bff",
            "scope": "openid profile email",
            "iat": now,
            "exp": now + 300,
        } | claim_overrides
        return jwt.encode(claims, self.private_key, algorithm="RS256", headers={"kid": kid})

    def _handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/.well-known/openid-configuration"):
            return httpx.Response(
                200, json={"issuer": ISSUER, "jwks_uri": f"{ISSUER}/protocol/openid-connect/certs"}
            )
        if request.url.path.endswith("/certs"):
            self.jwks_requests += 1
            jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.private_key.public_key()))
            return httpx.Response(200, json={"keys": [jwk | {"kid": KEY_ID, "use": "sig"}]})
        return httpx.Response(404)


@pytest.fixture
def issuer() -> FakeIssuer:
    return FakeIssuer()


@pytest.fixture
async def client(
    issuer: FakeIssuer,
    database_url: str,
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[httpx.AsyncClient]:
    settings = Settings(issuer=ISSUER, audience=AUDIENCE, database_url=database_url)
    async with httpx.AsyncClient(transport=issuer.transport()) as outbound:
        app = create_app(settings, http_client=outbound, session_factory=session_factory)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://api.test"
        ) as api:
            yield api


BearerFactory = Callable[..., dict[str, str]]


@pytest.fixture
def bearer(issuer: FakeIssuer) -> BearerFactory:
    def make(**claims: Any) -> dict[str, str]:
        return {"Authorization": f"Bearer {issuer.token(**claims)}"}

    return make
