"""Resource server application factory.

Run with: uvicorn app.main:create_app --factory --port 8001
"""

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.api import notes
from app.clock import Clock
from app.config import Settings
from app.dependencies import build_container
from app.errors import InvalidTokenError, KeySetUnavailableError

logger = logging.getLogger(__name__)

REALM = "demo-api"


def create_app(
    settings: Settings | None = None,
    *,
    http_client: httpx.AsyncClient | None = None,
    clock: Clock = time.monotonic,
) -> FastAPI:
    settings = settings or Settings()
    http = http_client or httpx.AsyncClient(timeout=settings.http_timeout_seconds)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        if http_client is None:
            await http.aclose()

    app = FastAPI(title="Demo notes API", lifespan=lifespan)
    app.state.container = build_container(settings, http, clock)
    app.include_router(notes.router)

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.exception_handler(InvalidTokenError)
    async def handle_invalid_token(request: Request, exc: InvalidTokenError) -> JSONResponse:
        # RFC 6750: say which scheme is expected, and add error="invalid_token" only
        # when a token was sent.
        challenge = f'Bearer realm="{REALM}"'
        if exc.token_present:
            challenge += ', error="invalid_token"'
            logger.info("%s", exc)
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Invalid or missing access token"},
            headers={"WWW-Authenticate": challenge},
        )

    @app.exception_handler(KeySetUnavailableError)
    async def handle_key_set(request: Request, exc: KeySetUnavailableError) -> JSONResponse:
        logger.error("%s", exc)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "Cannot verify tokens right now"},
        )

    return app
