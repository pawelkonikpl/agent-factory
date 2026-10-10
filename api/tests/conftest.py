import json
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.config import Settings
from app.main import create_app

ISSUER = "https://idp.test/realms/demo"
AUDIENCE = "demo-api"
KEY_ID = "test-key-1"


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
async def client(issuer: FakeIssuer) -> AsyncIterator[httpx.AsyncClient]:
    settings = Settings(issuer=ISSUER, audience=AUDIENCE)
    async with httpx.AsyncClient(transport=issuer.transport()) as outbound:
        app = create_app(settings, http_client=outbound)
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
