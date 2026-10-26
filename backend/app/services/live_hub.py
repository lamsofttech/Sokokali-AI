"""Fan-out of live broadcast messages to WebSocket clients (the dashboard, later the stream overlay)."""

import asyncio
from collections import deque
from datetime import UTC, datetime
from typing import Any


class LiveHub:
    def __init__(self, history: int = 50, client_buffer: int = 200) -> None:
        self._clients: set[asyncio.Queue[dict[str, Any]]] = set()
        self._recent: deque[dict[str, Any]] = deque(maxlen=history)
        self._client_buffer = client_buffer

    def publish(self, kind: str, data: Any) -> dict[str, Any]:
        message = {"type": kind, "at": datetime.now(UTC).isoformat(), "data": data}
        if kind in ("event", "say", "game"):
            self._recent.append(message)
        for queue in self._clients:
            if queue.full():  # a slow client loses its oldest messages, never blocks the broadcast
                queue.get_nowait()
            queue.put_nowait(message)
        return message

    def connect(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self._client_buffer)
        self._clients.add(queue)
        return queue

    def disconnect(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._clients.discard(queue)

    def recent(self) -> list[dict[str, Any]]:
        return list(self._recent)

    @property
    def client_count(self) -> int:
        return len(self._clients)
