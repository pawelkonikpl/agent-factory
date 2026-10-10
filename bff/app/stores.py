"""Key-value storage with expiry for login transactions and sessions."""

from collections.abc import Callable
from typing import Generic, Protocol, TypeVar

T = TypeVar("T")
Clock = Callable[[], float]


class TtlStore(Protocol[T]):
    async def get(self, key: str) -> T | None: ...

    async def set(self, key: str, value: T, ttl_seconds: float) -> None: ...

    async def pop(self, key: str) -> T | None: ...

    async def delete(self, key: str) -> None: ...


class InMemoryTtlStore(Generic[T]):
    """Process-local store for development.

    With more than one worker or instance, use a shared store such as Redis;
    otherwise a session only exists in the process that created it.
    """

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._items: dict[str, tuple[T, float]] = {}

    async def get(self, key: str) -> T | None:
        item = self._items.get(key)
        if item is None:
            return None
        value, expires_at = item
        if expires_at <= self._clock():
            del self._items[key]
            return None
        return value

    async def set(self, key: str, value: T, ttl_seconds: float) -> None:
        self._purge_expired()
        self._items[key] = (value, self._clock() + ttl_seconds)

    async def pop(self, key: str) -> T | None:
        value = await self.get(key)
        self._items.pop(key, None)
        return value

    async def delete(self, key: str) -> None:
        self._items.pop(key, None)

    def _purge_expired(self) -> None:
        now = self._clock()
        expired = [key for key, (_, expires_at) in self._items.items() if expires_at <= now]
        for key in expired:
            del self._items[key]
