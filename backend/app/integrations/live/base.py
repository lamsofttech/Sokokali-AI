"""Interface for livestream platform connectors (simulated, TikTok, YouTube, ...)."""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

from app.schemas.live import LiveEvent

EventCallback = Callable[[LiveEvent], Awaitable[None]]


class LiveSourceUnavailableError(Exception):
    """The connector cannot run (not authorized, not configured, platform down)."""


class LiveEventSource(ABC):
    name: str
    is_simulated: bool

    async def check(self) -> None:
        """Fail fast before starting: raise LiveSourceUnavailableError if the source can never run."""

    @abstractmethod
    async def run(self, emit: EventCallback) -> None:
        """Receive events and pass each one to ``emit`` until cancelled.

        Raise ``LiveSourceUnavailableError`` for problems that retrying won't fix
        (missing credentials); any other exception is treated as temporary and the
        broadcast controller reconnects with backoff.
        """
