"""Fire-and-forget background tasks that are tracked (not garbage-collected mid-flight) and logged on failure."""

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

logger = logging.getLogger(__name__)

_tasks: set[asyncio.Task[Any]] = set()


def spawn(coro: Coroutine[Any, Any, Any], name: str = "background") -> asyncio.Task[Any]:
    task = asyncio.create_task(coro, name=name)
    _tasks.add(task)

    def done(t: asyncio.Task[Any]) -> None:
        _tasks.discard(t)
        if not t.cancelled() and t.exception() is not None:
            logger.warning("background_task_failed", extra={"task": name, "error": str(t.exception())})

    task.add_done_callback(done)
    return task


async def drain(timeout: float = 5.0) -> None:
    """Wait for pending background work (e.g. database writes) during shutdown."""
    if _tasks:
        await asyncio.wait(set(_tasks), timeout=timeout)
