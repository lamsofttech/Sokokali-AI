"""Bounded per-viewer conversation history with expiry.

In-process only; Phase 2 moves this to Redis so context survives restarts and
is shared across replicas.
"""

import time
from collections import deque
from dataclasses import dataclass, field

from app.schemas.chat import Intent


@dataclass(frozen=True)
class Turn:
    message: str
    reply: str
    intent: Intent
    team_ids: tuple[str, ...]
    at: float


@dataclass
class _Conversation:
    turns: deque[Turn]
    last_seen: float = field(default_factory=time.monotonic)


class ConversationMemory:
    def __init__(self, max_turns: int = 10, ttl_seconds: float = 1800, max_viewers: int = 10_000) -> None:
        self.max_turns = max_turns
        self.ttl_seconds = ttl_seconds
        self.max_viewers = max_viewers
        self._conversations: dict[str, _Conversation] = {}

    def history(self, viewer_id: str) -> list[Turn]:
        conversation = self._conversations.get(viewer_id)
        if conversation is None or time.monotonic() - conversation.last_seen > self.ttl_seconds:
            self._conversations.pop(viewer_id, None)
            return []
        return list(conversation.turns)

    def last_team_ids(self, viewer_id: str) -> tuple[str, ...]:
        for turn in reversed(self.history(viewer_id)):
            if turn.team_ids:
                return turn.team_ids
        return ()

    def add(self, viewer_id: str, turn: Turn) -> None:
        conversation = self._conversations.get(viewer_id)
        if conversation is None:
            self._evict_if_full()
            conversation = _Conversation(turns=deque(maxlen=self.max_turns))
            self._conversations[viewer_id] = conversation
        conversation.turns.append(turn)
        conversation.last_seen = time.monotonic()

    def _evict_if_full(self) -> None:
        now = time.monotonic()
        for viewer_id in [v for v, c in self._conversations.items() if now - c.last_seen > self.ttl_seconds]:
            del self._conversations[viewer_id]
        if len(self._conversations) >= self.max_viewers:
            oldest = min(self._conversations, key=lambda v: self._conversations[v].last_seen)
            del self._conversations[oldest]

    def __len__(self) -> int:
        return len(self._conversations)
