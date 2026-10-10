"""Time source, injectable so tests can move time."""

from collections.abc import Callable

Clock = Callable[[], float]
