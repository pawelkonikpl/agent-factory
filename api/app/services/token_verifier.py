"""Validates JWT access tokens issued by the authorization server."""

from dataclasses import dataclass
from typing import Any

import httpx
import jwt

from app.clock import Clock
from app.config import Settings
from app.errors import InvalidTokenError, KeySetUnavailableError

DISCOVERY_PATH = "/.well-known/openid-configuration"
# Asymmetric algorithms only: accepting HS256 would let anyone who knows a public key
# forge tokens (algorithm confusion), and "none" is never acceptable.
SIGNING_ALGORITHMS = frozenset({"RS256", "PS256", "ES256"})
CLOCK_SKEW_SECONDS = 30


@dataclass(frozen=True)
class Principal:
    """Who is calling: the user (sub) and the client acting for them (azp)."""

    subject: str
    client_id: str | None
    scopes: frozenset[str]


class AccessTokenVerifier:
    def __init__(self, settings: Settings, http: httpx.AsyncClient, clock: Clock) -> None:
        self._settings = settings
        self._http = http
        self._clock = clock
        self._jwks_uri: str | None = None
        self._keys: jwt.PyJWKSet | None = None
        self._keys_loaded_at = float("-inf")

    async def verify(self, token: str) -> Principal:
        try:
            kid = jwt.get_unverified_header(token).get("kid")
            key = await self._signing_key(kid)
            claims: dict[str, Any] = jwt.decode(
                token,
                key.key,
                algorithms=[key.algorithm_name],
                audience=self._settings.audience,
                issuer=self._settings.issuer,
                leeway=CLOCK_SKEW_SECONDS,
                options={"require": ["iss", "sub", "aud", "exp"]},
            )
        except jwt.PyJWTError as exc:
            raise InvalidTokenError(f"Access token rejected: {exc}") from exc
        return Principal(
            subject=str(claims["sub"]),
            client_id=claims.get("azp") or claims.get("client_id"),
            scopes=frozenset(str(claims.get("scope", "")).split()),
        )

    async def _signing_key(self, kid: str | None) -> jwt.PyJWK:
        key = self._find_key(await self._key_set(), kid)
        if key is None and self._may_refresh_keys():
            # Unknown kid: the issuer may have rotated keys. Refetching at most once per
            # interval stops tokens with random kids from hammering the issuer.
            key = self._find_key(await self._key_set(force_refresh=True), kid)
        if key is None:
            raise InvalidTokenError(f"No trusted signing key with kid {kid!r}")
        return key

    @staticmethod
    def _find_key(key_set: jwt.PyJWKSet, kid: str | None) -> jwt.PyJWK | None:
        for key in key_set.keys:
            if key.key_id == kid and key.algorithm_name in SIGNING_ALGORITHMS:
                return key
        return None

    def _may_refresh_keys(self) -> bool:
        elapsed = self._clock() - self._keys_loaded_at
        return elapsed >= self._settings.jwks_min_refresh_interval_seconds

    async def _key_set(self, *, force_refresh: bool = False) -> jwt.PyJWKSet:
        if self._keys is None or force_refresh:
            document = await self._get_json(await self._discover_jwks_uri())
            signing_keys = [key for key in document.get("keys", []) if key.get("use") != "enc"]
            try:
                self._keys = jwt.PyJWKSet.from_dict({"keys": signing_keys})
            except jwt.PyJWKSetError as exc:
                raise KeySetUnavailableError("Issuer JWKS has no usable signing keys") from exc
            self._keys_loaded_at = self._clock()
        return self._keys

    async def _discover_jwks_uri(self) -> str:
        if self._jwks_uri is None:
            metadata = await self._get_json(self._settings.issuer.rstrip("/") + DISCOVERY_PATH)
            if metadata.get("issuer") != self._settings.issuer:
                raise KeySetUnavailableError("Discovery document names a different issuer")
            self._jwks_uri = str(metadata["jwks_uri"])
        return self._jwks_uri

    async def _get_json(self, url: str) -> dict[str, Any]:
        try:
            response = await self._http.get(url, headers={"Accept": "application/json"})
            response.raise_for_status()
            document: dict[str, Any] = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise KeySetUnavailableError(f"Could not load {url}") from exc
        return document
