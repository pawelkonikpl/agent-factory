"""In-process authorization server and resource server for tests.

Plugged into the BFF's httpx client through httpx.MockTransport. It enforces the parts
of OAuth the BFF relies on: PKCE S256, one-time codes, client authentication and
refresh token rotation.
"""

import asyncio
import base64
import hashlib
import json
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

ISSUER = "https://idp.test/realms/demo"
API_BASE_URL = "https://api.test"
CLIENT_ID = "demo-bff"
CLIENT_SECRET = "test-secret"
REDIRECT_URI = "https://app.test/bff/callback"
KEY_ID = "test-key-1"
ACCESS_TOKEN_LIFETIME = 300
# Lets other requests run while one waits for the token endpoint, like real network I/O.
TOKEN_ENDPOINT_LATENCY_SECONDS = 0.01


@dataclass
class IssuedCode:
    code_challenge: str
    redirect_uri: str
    nonce: str
    subject: str


@dataclass
class FakeAuthorizationServer:
    clock: Callable[[], float]
    private_key: rsa.RSAPrivateKey = field(
        default_factory=lambda: rsa.generate_private_key(public_exponent=65537, key_size=2048)
    )
    codes: dict[str, IssuedCode] = field(default_factory=dict)
    active_refresh_tokens: dict[str, str] = field(default_factory=dict)
    revoked_tokens: list[str] = field(default_factory=list)
    token_requests: list[dict[str, str]] = field(default_factory=list)
    api_requests: list[httpx.Request] = field(default_factory=list)
    issuer_in_response: str = ISSUER

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def authorize(self, authorization_url: str, subject: str = "alice") -> str:
        """Plays the user logging in and consenting. Returns the redirect back to the BFF."""
        params = {
            key: values[0] for key, values in parse_qs(urlsplit(authorization_url).query).items()
        }
        assert params["response_type"] == "code"
        assert params["client_id"] == CLIENT_ID
        assert params["code_challenge_method"] == "S256"
        code = secrets.token_urlsafe(16)
        self.codes[code] = IssuedCode(
            code_challenge=params["code_challenge"],
            redirect_uri=params["redirect_uri"],
            nonce=params["nonce"],
            subject=subject,
        )
        query = urlencode({"code": code, "state": params["state"], "iss": self.issuer_in_response})
        return f"{params['redirect_uri']}?{query}"

    async def _handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == urlsplit(API_BASE_URL).hostname:
            return self._handle_api(request)
        path = request.url.path.removeprefix(urlsplit(ISSUER).path)
        if path == "/.well-known/openid-configuration":
            return httpx.Response(200, json=self._metadata())
        if path == "/protocol/openid-connect/certs":
            return httpx.Response(200, json=self._jwks())
        if path == "/protocol/openid-connect/token":
            await asyncio.sleep(TOKEN_ENDPOINT_LATENCY_SECONDS)
            return self._handle_token(request)
        if path == "/protocol/openid-connect/revoke":
            form = _form(request)
            self.revoked_tokens.append(form["token"])
            self.active_refresh_tokens.pop(form["token"], None)
            return httpx.Response(200)
        return httpx.Response(404)

    def _handle_token(self, request: httpx.Request) -> httpx.Response:
        form = _form(request)
        self.token_requests.append(form)
        if form.get("client_id") != CLIENT_ID or form.get("client_secret") != CLIENT_SECRET:
            return _oauth_error("invalid_client", status_code=401)
        if form["grant_type"] == "authorization_code":
            issued = self.codes.pop(form["code"], None)  # one-time use
            if issued is None or issued.redirect_uri != form.get("redirect_uri"):
                return _oauth_error("invalid_grant")
            if _s256(form.get("code_verifier", "")) != issued.code_challenge:
                return _oauth_error("invalid_grant")
            return self._issue_tokens(issued.subject, nonce=issued.nonce)
        if form["grant_type"] == "refresh_token":
            # Rotation: every refresh token works exactly once.
            subject = self.active_refresh_tokens.pop(form["refresh_token"], None)
            if subject is None:
                return _oauth_error("invalid_grant")
            return self._issue_tokens(subject, nonce=None)
        return _oauth_error("unsupported_grant_type")

    def _issue_tokens(self, subject: str, *, nonce: str | None) -> httpx.Response:
        refresh_token = f"rt-{secrets.token_urlsafe(16)}"
        self.active_refresh_tokens[refresh_token] = subject
        now = int(self.clock())
        claims: dict[str, Any] = {
            "iss": ISSUER,
            "sub": subject,
            "aud": CLIENT_ID,
            "iat": now,
            "exp": now + ACCESS_TOKEN_LIFETIME,
            "name": subject.title(),
            "email": f"{subject}@example.com",
        }
        if nonce is not None:
            claims["nonce"] = nonce
        id_token = jwt.encode(claims, self.private_key, algorithm="RS256", headers={"kid": KEY_ID})
        return httpx.Response(
            200,
            json={
                "access_token": f"at-{secrets.token_urlsafe(16)}",
                "token_type": "Bearer",
                "expires_in": ACCESS_TOKEN_LIFETIME,
                "refresh_token": refresh_token,
                "id_token": id_token,
            },
        )

    def _handle_api(self, request: httpx.Request) -> httpx.Response:
        self.api_requests.append(request)
        return httpx.Response(
            200,
            json={
                "path": request.url.path,
                "query": request.url.query.decode(),
                "authorization": request.headers.get("authorization"),
                "cookie": request.headers.get("cookie"),
                "body": request.content.decode(),
            },
        )

    def _metadata(self) -> dict[str, Any]:
        base = f"{ISSUER}/protocol/openid-connect"
        return {
            "issuer": ISSUER,
            "authorization_endpoint": f"{base}/auth",
            "token_endpoint": f"{base}/token",
            "jwks_uri": f"{base}/certs",
            "end_session_endpoint": f"{base}/logout",
            "revocation_endpoint": f"{base}/revoke",
            "code_challenge_methods_supported": ["plain", "S256"],
            "authorization_response_iss_parameter_supported": True,
        }

    def _jwks(self) -> dict[str, Any]:
        public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.private_key.public_key()))
        public_jwk |= {"kid": KEY_ID, "use": "sig", "alg": "RS256"}
        # An encryption key like the one Keycloak publishes; the BFF must skip it.
        encryption_jwk = public_jwk | {"kid": "enc-key", "use": "enc", "alg": "RSA-OAEP"}
        return {"keys": [encryption_jwk, public_jwk]}


def _form(request: httpx.Request) -> dict[str, str]:
    return {key: values[0] for key, values in parse_qs(request.content.decode()).items()}


def _s256(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def _oauth_error(error: str, status_code: int = 400) -> httpx.Response:
    return httpx.Response(status_code, json={"error": error})
