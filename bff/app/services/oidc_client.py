"""OAuth 2.1 / OpenID Connect client for the authorization server.

The BFF is a confidential client (RFC 10017): it authenticates at the token endpoint,
and the tokens it receives never leave the server.
"""

from typing import Any

import httpx
import jwt
from pydantic import BaseModel, ConfigDict, Field

from app.config import Settings
from app.errors import InvalidIdTokenError, ProviderError, TokenEndpointError
from app.services.crypto import constant_time_equals

DISCOVERY_PATH = "/.well-known/openid-configuration"
# Asymmetric algorithms only, so a token can never be "signed" with a shared secret.
SIGNING_ALGORITHMS = frozenset({"RS256", "PS256", "ES256"})
CLOCK_SKEW_SECONDS = 30


class ProviderMetadata(BaseModel):
    model_config = ConfigDict(extra="ignore")

    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    end_session_endpoint: str | None = None
    revocation_endpoint: str | None = None
    code_challenge_methods_supported: list[str] = Field(default_factory=list)
    authorization_response_iss_parameter_supported: bool = False


class TokenResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    access_token: str
    token_type: str
    expires_in: int
    refresh_token: str | None = None
    id_token: str | None = None


class OidcClient:
    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http
        self._metadata: ProviderMetadata | None = None
        self._jwks: jwt.PyJWKSet | None = None

    async def metadata(self) -> ProviderMetadata:
        """Discovery document, fetched once and checked against the configured issuer."""
        if self._metadata is not None:
            return self._metadata
        url = self._settings.issuer.rstrip("/") + DISCOVERY_PATH
        try:
            metadata = ProviderMetadata.model_validate(await self._get_json(url))
        except ValueError as exc:
            raise ProviderError(f"Malformed discovery document at {url}") from exc
        if metadata.issuer != self._settings.issuer:
            raise ProviderError(
                f"Discovery issuer {metadata.issuer!r} differs from {self._settings.issuer!r}"
            )
        if "S256" not in metadata.code_challenge_methods_supported:
            raise ProviderError("Authorization server does not advertise PKCE S256")
        self._metadata = metadata
        return metadata

    async def authorization_url(self, *, state: str, nonce: str, code_challenge: str) -> str:
        metadata = await self.metadata()
        params = {
            "response_type": "code",
            "client_id": self._settings.client_id,
            "redirect_uri": self._settings.redirect_uri,
            "scope": self._settings.scope,
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        # copy_merge_params keeps any query the endpoint already has, as OAuth requires.
        return str(httpx.URL(metadata.authorization_endpoint).copy_merge_params(params))

    async def is_expected_issuer(self, iss: str | None) -> bool:
        """RFC 9207 mix-up defense: the authorization response must name our issuer."""
        metadata = await self.metadata()
        if iss is None:
            return not metadata.authorization_response_iss_parameter_supported
        return iss == metadata.issuer

    async def exchange_code(self, code: str, code_verifier: str) -> TokenResponse:
        return await self._token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self._settings.redirect_uri,
                "code_verifier": code_verifier,
            }
        )

    async def refresh(self, refresh_token: str) -> TokenResponse:
        return await self._token_request(
            {"grant_type": "refresh_token", "refresh_token": refresh_token}
        )

    async def revoke_refresh_token(self, refresh_token: str) -> None:
        """RFC 7009 revocation. Does nothing when the server has no revocation endpoint."""
        metadata = await self.metadata()
        if metadata.revocation_endpoint is None:
            return
        form = {"token": refresh_token, "token_type_hint": "refresh_token"}
        response = await self._post_form(metadata.revocation_endpoint, form)
        if response.status_code != httpx.codes.OK:
            raise ProviderError(f"Revocation endpoint returned {response.status_code}")

    async def end_session_url(self, id_token_hint: str) -> str | None:
        """OpenID Connect RP-initiated logout URL for the browser, if the server has one."""
        metadata = await self.metadata()
        if metadata.end_session_endpoint is None:
            return None
        params = {
            "client_id": self._settings.client_id,
            "id_token_hint": id_token_hint,
            "post_logout_redirect_uri": self._settings.post_logout_redirect_uri,
        }
        return str(httpx.URL(metadata.end_session_endpoint).copy_merge_params(params))

    async def validate_id_token(self, id_token: str, *, nonce: str) -> dict[str, Any]:
        metadata = await self.metadata()
        try:
            key = await self._signing_key(id_token)
            claims: dict[str, Any] = jwt.decode(
                id_token,
                key.key,
                algorithms=[key.algorithm_name],
                audience=self._settings.client_id,
                issuer=metadata.issuer,
                leeway=CLOCK_SKEW_SECONDS,
                options={"require": ["iss", "sub", "aud", "exp", "iat"]},
            )
        except jwt.PyJWTError as exc:
            raise InvalidIdTokenError(f"ID token rejected: {exc}") from exc
        if not constant_time_equals(str(claims.get("nonce", "")), nonce):
            raise InvalidIdTokenError("ID token nonce does not match the login request")
        audiences = claims["aud"] if isinstance(claims["aud"], list) else [claims["aud"]]
        if len(audiences) > 1 and claims.get("azp") != self._settings.client_id:
            raise InvalidIdTokenError("ID token has several audiences and a foreign azp")
        return claims

    async def _signing_key(self, token: str) -> jwt.PyJWK:
        kid = jwt.get_unverified_header(token).get("kid")
        # A kid we do not know may mean the server rotated its keys: refetch once.
        for force_refresh in (False, True):
            for key in (await self._jwk_set(force_refresh=force_refresh)).keys:
                if key.key_id == kid and key.algorithm_name in SIGNING_ALGORITHMS:
                    return key
        raise InvalidIdTokenError(f"No usable signing key with kid {kid!r}")

    async def _jwk_set(self, *, force_refresh: bool) -> jwt.PyJWKSet:
        if self._jwks is None or force_refresh:
            metadata = await self.metadata()
            document = await self._get_json(metadata.jwks_uri)
            signing_keys = [key for key in document.get("keys", []) if key.get("use") != "enc"]
            try:
                self._jwks = jwt.PyJWKSet.from_dict({"keys": signing_keys})
            except jwt.PyJWKSetError as exc:
                raise ProviderError("JWKS has no usable signing keys") from exc
        return self._jwks

    async def _token_request(self, form: dict[str, str]) -> TokenResponse:
        metadata = await self.metadata()
        response = await self._post_form(metadata.token_endpoint, form)
        if response.status_code != httpx.codes.OK:
            raise TokenEndpointError(_oauth_error_code(response), response.status_code)
        try:
            tokens = TokenResponse.model_validate(response.json())
        except ValueError as exc:
            raise ProviderError("Malformed token endpoint response") from exc
        if tokens.token_type.lower() != "bearer":
            raise ProviderError(f"Unsupported token type {tokens.token_type!r}")
        return tokens

    async def _post_form(self, url: str, form: dict[str, str]) -> httpx.Response:
        # client_secret_post: OAuth 2.1 prefers credentials in the body over HTTP Basic,
        # because Basic needs extra form-encoding that implementations often get wrong.
        body = form | {
            "client_id": self._settings.client_id,
            "client_secret": self._settings.client_secret.get_secret_value(),
        }
        try:
            return await self._http.post(url, data=body, headers={"Accept": "application/json"})
        except httpx.HTTPError as exc:
            raise ProviderError(f"Authorization server unreachable at {url}") from exc

    async def _get_json(self, url: str) -> dict[str, Any]:
        try:
            response = await self._http.get(url, headers={"Accept": "application/json"})
            response.raise_for_status()
            document: dict[str, Any] = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError(f"Could not load {url}") from exc
        return document


def _oauth_error_code(response: httpx.Response) -> str:
    try:
        return str(response.json().get("error", "unknown_error"))
    except ValueError:
        return "unknown_error"
