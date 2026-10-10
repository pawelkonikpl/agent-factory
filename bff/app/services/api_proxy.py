"""Forwards the SPA's API calls to the resource server with the user's access token."""

from collections.abc import Mapping
from dataclasses import dataclass

import httpx

from app.errors import UpstreamPathError, UpstreamUnavailableError

# Only these headers pass through. Cookies in particular stay at the BFF.
FORWARDED_REQUEST_HEADERS = frozenset(
    {"accept", "accept-language", "content-type", "if-match", "if-none-match"}
)
FORWARDED_RESPONSE_HEADERS = frozenset({"content-type", "cache-control", "etag", "last-modified"})


@dataclass(frozen=True)
class ProxiedResponse:
    status_code: int
    headers: dict[str, str]
    content: bytes


class ApiProxy:
    """Calls exactly one resource server (RFC 10017: strict outbound request control)."""

    def __init__(self, http: httpx.AsyncClient, base_url: str) -> None:
        self._http = http
        self._base_url = httpx.URL(base_url)

    def upstream_url(self, path: str, query: str) -> httpx.URL:
        if any(segment in {".", ".."} for segment in path.split("/")):
            raise UpstreamPathError(path)
        base_path = self._base_url.path.rstrip("/")
        # copy_with keeps scheme, host and port from the configured base URL, and
        # percent-encodes "?" or "#" in the path, so neither can change the target.
        return self._base_url.copy_with(
            path=f"{base_path}/{path.lstrip('/')}", query=query.encode() or None
        )

    async def forward(
        self,
        *,
        method: str,
        path: str,
        query: str,
        headers: Mapping[str, str],
        body: bytes,
        access_token: str,
    ) -> ProxiedResponse:
        url = self.upstream_url(path, query)
        outgoing = {
            name: value
            for name, value in headers.items()
            if name.lower() in FORWARDED_REQUEST_HEADERS
        }
        outgoing["Authorization"] = f"Bearer {access_token}"
        try:
            response = await self._http.request(method, url, headers=outgoing, content=body)
        except httpx.HTTPError as exc:
            raise UpstreamUnavailableError(f"Resource server unreachable: {url}") from exc
        return ProxiedResponse(
            status_code=response.status_code,
            headers={
                name: value
                for name, value in response.headers.items()
                if name.lower() in FORWARDED_RESPONSE_HEADERS
            },
            content=response.content,
        )
