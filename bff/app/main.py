"""BFF application factory.

Run with: uvicorn app.main:create_app --factory --port 8000
"""

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, RedirectResponse

from app.api import proxy, session
from app.config import Settings
from app.dependencies import build_container, get_container
from app.errors import (
    CsrfError,
    LoginError,
    NotAuthenticatedError,
    ProviderError,
    UpstreamPathError,
    UpstreamUnavailableError,
)
from app.security import clear_login_cookie, clear_session_cookie
from app.stores import Clock

logger = logging.getLogger(__name__)

LOGIN_ERROR_REDIRECT = "/?login_error={code}"


def create_app(
    settings: Settings | None = None,
    *,
    http_client: httpx.AsyncClient | None = None,
    clock: Clock = time.time,
) -> FastAPI:
    settings = settings or Settings()
    http = http_client or httpx.AsyncClient(timeout=settings.http_timeout_seconds)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        if http_client is None:
            await http.aclose()

    # No interactive docs: this app is an extension of the SPA, not a public API.
    app = FastAPI(title="Demo BFF", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.container = build_container(settings, http, clock)
    app.include_router(session.router)
    app.include_router(proxy.router)
    _register_exception_handlers(app)
    return app


def _register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(LoginError)
    async def handle_login_error(request: Request, exc: LoginError) -> RedirectResponse:
        logger.warning("Login failed (%s): %s", exc.code, exc)
        response = RedirectResponse(
            LOGIN_ERROR_REDIRECT.format(code=exc.code), status_code=status.HTTP_303_SEE_OTHER
        )
        clear_login_cookie(response, get_container(request).settings)
        return response

    @app.exception_handler(NotAuthenticatedError)
    async def handle_not_authenticated(
        request: Request, exc: NotAuthenticatedError
    ) -> JSONResponse:
        response = JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED, content={"detail": "Not authenticated"}
        )
        clear_session_cookie(response, get_container(request).settings)
        return response

    @app.exception_handler(CsrfError)
    async def handle_csrf(request: Request, exc: CsrfError) -> JSONResponse:
        logger.warning("CSRF check failed for %s %s: %s", request.method, request.url.path, exc)
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN, content={"detail": "CSRF check failed"}
        )

    @app.exception_handler(UpstreamPathError)
    async def handle_upstream_path(request: Request, exc: UpstreamPathError) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": str(exc)})

    @app.exception_handler(UpstreamUnavailableError)
    async def handle_upstream_unavailable(
        request: Request, exc: UpstreamUnavailableError
    ) -> JSONResponse:
        logger.error("%s", exc)
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY, content={"detail": "API unavailable"}
        )

    @app.exception_handler(ProviderError)
    async def handle_provider(request: Request, exc: ProviderError) -> JSONResponse:
        logger.error("Authorization server error: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"detail": "Authorization server error"},
        )
