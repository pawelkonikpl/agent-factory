"""Hands out a valid access token for a session, refreshing it when needed."""

import asyncio
from dataclasses import replace
from weakref import WeakValueDictionary

from app.config import Settings
from app.errors import NotAuthenticatedError, TokenEndpointError
from app.models import TokenSet, UserSession
from app.services.auth_service import token_set_from_response
from app.services.oidc_client import OidcClient
from app.session_repository import SessionRepository
from app.stores import Clock


class TokenService:
    def __init__(
        self,
        settings: Settings,
        oidc: OidcClient,
        sessions: SessionRepository,
        clock: Clock,
    ) -> None:
        self._settings = settings
        self._oidc = oidc
        self._sessions = sessions
        self._clock = clock
        # One lock per session. With refresh token rotation, two parallel refreshes would
        # present the same refresh token twice, and the server would treat that as theft
        # and revoke the whole grant. The lock is per process; several BFF instances
        # need a distributed lock (e.g. in Redis) instead.
        self._locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()

    async def access_token_for(self, session: UserSession) -> str:
        if not self._is_expiring(session.tokens):
            return session.tokens.access_token
        lock = self._lock_for(session.session_id)
        async with lock:
            # Another request may have refreshed the tokens while this one waited.
            current = await self._sessions.get(session.session_id)
            if current is None:
                raise NotAuthenticatedError("Session ended while waiting for token refresh")
            if not self._is_expiring(current.tokens):
                return current.tokens.access_token
            return (await self._refresh(current)).tokens.access_token

    async def _refresh(self, session: UserSession) -> UserSession:
        refresh_token = session.tokens.refresh_token
        if refresh_token is None:
            await self._sessions.delete(session.session_id)
            raise NotAuthenticatedError("Access token expired and there is no refresh token")
        try:
            response = await self._oidc.refresh(refresh_token)
        except TokenEndpointError as exc:
            if exc.error != "invalid_grant":
                raise
            # The refresh token expired, was revoked or was reused. RFC 10017: once the
            # BFF learns that, the session is over and the user has to log in again.
            await self._sessions.delete(session.session_id)
            raise NotAuthenticatedError("Refresh token was rejected") from exc
        tokens = token_set_from_response(
            response,
            now=self._clock(),
            id_token=response.id_token or session.tokens.id_token,
        )
        if tokens.refresh_token is None:
            # Servers without rotation may omit it; the old one stays valid then.
            tokens = replace(tokens, refresh_token=refresh_token)
        updated = replace(session, tokens=tokens)
        await self._sessions.save(updated)
        return updated

    def _is_expiring(self, tokens: TokenSet) -> bool:
        margin = self._settings.token_refresh_margin_seconds
        return tokens.access_token_expires_at - margin <= self._clock()

    def _lock_for(self, session_id: str) -> asyncio.Lock:
        lock = self._locks.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[session_id] = lock
        return lock
