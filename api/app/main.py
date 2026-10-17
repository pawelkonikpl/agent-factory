"""Resource server application factory.

Run with: uvicorn app.main:create_app --factory --port 8001
"""

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.api import campaigns, categories, clients, config, emails, notes
from app.clock import Clock
from app.config import Settings
from app.database import create_engine, create_session_factory, run_migrations
from app.dependencies import Container, build_campaign_sender, build_container
from app.errors import DomainError, InvalidTokenError, KeySetUnavailableError, NotFoundError
from app.services.smtp_sender import EmailSenderFactory, SmtpEmailSender

logger = logging.getLogger(__name__)

REALM = "demo-api"


def create_app(
    settings: Settings | None = None,
    *,
    http_client: httpx.AsyncClient | None = None,
    clock: Clock = time.monotonic,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    email_sender_factory: EmailSenderFactory | None = None,
) -> FastAPI:
    settings = settings or Settings()
    http = http_client or httpx.AsyncClient(timeout=settings.http_timeout_seconds)
    # The app disposes only an engine it built; an injected factory belongs to the caller.
    engine: AsyncEngine | None = None
    if session_factory is None:
        engine = create_engine(settings.database_url)
        session_factory = create_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # The async env.py calls asyncio.run, which cannot run inside this loop.
        try:
            await asyncio.to_thread(run_migrations, settings.database_url)
        except Exception:
            logger.exception("Database migration failed")
            raise
        container: Container = app.state.container
        try:
            async with container.sessions() as session:
                await build_campaign_sender(container, session).recover_interrupted()
        except Exception:
            logger.exception("Recovering interrupted campaign sends failed")
            raise
        yield
        if http_client is None:
            await http.aclose()
        if engine is not None:
            await engine.dispose()

    app = FastAPI(title="Demo notes API", lifespan=lifespan)
    app.state.container = build_container(
        settings, http, clock, session_factory, email_sender_factory or SmtpEmailSender
    )
    app.include_router(notes.router)
    app.include_router(categories.router)
    app.include_router(clients.router)
    app.include_router(campaigns.router)
    app.include_router(emails.router)
    app.include_router(config.router)

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

    @app.exception_handler(DomainError)
    async def handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
        # The only place that maps domain errors to statuses: by type, never by message.
        if isinstance(exc, NotFoundError):
            status_code = status.HTTP_404_NOT_FOUND
        else:
            status_code = status.HTTP_400_BAD_REQUEST
        return JSONResponse(status_code=status_code, content={"detail": str(exc)})

    return app
