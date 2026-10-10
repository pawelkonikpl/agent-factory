"""Stores user sessions with an idle timeout and an absolute lifetime."""

from app.config import Settings
from app.models import UserSession
from app.stores import Clock, TtlStore


class SessionRepository:
    def __init__(self, store: TtlStore[UserSession], settings: Settings, clock: Clock) -> None:
        self._store = store
        self._settings = settings
        self._clock = clock

    async def get(self, session_id: str) -> UserSession | None:
        """Return the session and extend its idle timeout, or None when it has ended."""
        session = await self._store.get(session_id)
        if session is None:
            return None
        if self._remaining_lifetime(session) <= 0:
            await self._store.delete(session_id)
            return None
        await self.save(session)
        return session

    async def save(self, session: UserSession) -> None:
        ttl = min(self._settings.session_idle_timeout_seconds, self._remaining_lifetime(session))
        await self._store.set(session.session_id, session, ttl)

    async def pop(self, session_id: str) -> UserSession | None:
        return await self._store.pop(session_id)

    async def delete(self, session_id: str) -> None:
        await self._store.delete(session_id)

    def _remaining_lifetime(self, session: UserSession) -> float:
        ends_at = session.created_at + self._settings.session_absolute_timeout_seconds
        return ends_at - self._clock()
