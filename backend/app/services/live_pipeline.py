"""Comment intake for the livestream: validate, deduplicate, rate-limit, moderate, prioritize.

Only comments that deserve an on-air answer enter the queue. Priority rewards
real questions about matches and currencies, and first-time viewers. Gifts
never buy priority: free viewers get the same chance to be answered.
"""

import heapq
import itertools
import time
from collections import Counter, OrderedDict, defaultdict, deque
from dataclasses import dataclass, field

from app.integrations.sports.base import SportsDataError
from app.schemas.chat import Intent
from app.schemas.live import IngestResult, LiveEvent, LiveEventKind
from app.services.ai_engine import SokokaliAI
from app.services.forex_engine import ForexSignalEngine
from app.services.gamification import ANSWER_RE, POLL_OPTIONS
from app.services.sports_engine import SportsService

_ANSWERABLE = {Intent.PREDICTION, Intent.FIXTURES, Intent.RESULTS, Intent.TEAM_FORM, Intent.FOREX}


@dataclass(order=True)
class _Queued:
    sort_key: tuple[int, int]
    event: LiveEvent = field(compare=False)
    queued_at: float = field(compare=False)


class LiveEventPipeline:
    def __init__(
        self,
        ai: SokokaliAI,
        sports: SportsService,
        forex: ForexSignalEngine,
        max_queue: int = 50,
        dedup_ttl_seconds: float = 60,
        comments_per_viewer_per_minute: int = 4,
        max_comment_age_seconds: float = 90,
    ) -> None:
        self.ai = ai
        self.sports = sports
        self.forex = forex
        self.max_queue = max_queue
        self.dedup_ttl_seconds = dedup_ttl_seconds
        self.comments_per_viewer_per_minute = comments_per_viewer_per_minute
        self.max_comment_age_seconds = max_comment_age_seconds
        self._heap: list[_Queued] = []
        self._seq = itertools.count()
        self._seen_ids: OrderedDict[str, float] = OrderedDict()
        self._seen_texts: OrderedDict[tuple[str, str], float] = OrderedDict()
        self._viewer_hits: dict[str, deque[float]] = defaultdict(deque)
        self._viewers_answered_before: set[str] = set()
        self.rejected: Counter[str] = Counter()
        self.accepted = 0

    def _expire(self, now: float) -> None:
        for cache in (self._seen_ids, self._seen_texts):
            while cache and now - next(iter(cache.values())) > self.dedup_ttl_seconds:
                cache.popitem(last=False)

    def is_duplicate(self, event: LiveEvent, now: float | None = None) -> bool:
        """Same event delivered twice by the platform (any kind of event)."""
        now = time.monotonic() if now is None else now
        self._expire(now)
        if event.event_id in self._seen_ids:
            return True
        self._seen_ids[event.event_id] = now
        return False

    def _reject(self, reason: str) -> IngestResult:
        self.rejected[reason] += 1
        return IngestResult(accepted=False, reason=reason)

    async def ingest(self, event: LiveEvent, now: float | None = None) -> IngestResult:
        """Queue a comment for an on-air answer, or say why not. Call after ``is_duplicate``."""
        now = time.monotonic() if now is None else now
        if event.kind != LiveEventKind.COMMENT:
            return self._reject("not_a_comment")
        text = (event.text or "").strip()
        if len(text) < 3:
            return self._reject("too_short")  # "A", "X", emoji: not questions
        lowered = text.lower()
        if ANSWER_RE.match(lowered) or lowered in POLL_OPTIONS:
            return self._reject("game_answer")  # "jibu ni B": counted by gamification, not answered on air

        key = (f"{event.platform}:{event.viewer_id}", " ".join(text.lower().split()))
        if key in self._seen_texts:
            return self._reject("repeated_comment")
        self._seen_texts[key] = now

        hits = self._viewer_hits[key[0]]
        while hits and now - hits[0] >= 60:
            hits.popleft()
        if len(hits) >= self.comments_per_viewer_per_minute:
            return self._reject("rate_limited")
        hits.append(now)

        if self.ai.moderate(text) is not None:
            return self._reject("moderated")

        priority = await self._priority(event, text, key[0])
        heapq.heappush(self._heap, _Queued((-priority, next(self._seq)), event, now))
        if len(self._heap) > self.max_queue:
            # Drop the lowest-priority comment (the largest sort key).
            self._heap.remove(max(self._heap))
            heapq.heapify(self._heap)
            self.rejected["queue_full"] += 1
        self.accepted += 1
        return IngestResult(accepted=True, priority=priority)

    async def _priority(self, event: LiveEvent, text: str, viewer_key: str) -> int:
        try:
            teams = await self.sports.find_teams(text)
        except SportsDataError:
            teams = []  # data provider down: still answerable, just scored lower
        pairs = await self.forex.find_pairs(text)
        intent = self.ai.classify_intent(text, len(teams), len(pairs))
        score = 10
        if "?" in text:
            score += 10
        if teams or pairs:
            score += 15
        if intent in _ANSWERABLE:
            score += 10
        elif intent == Intent.GREETING:
            score -= 5
        if viewer_key not in self._viewers_answered_before:
            score += 5
        return score

    def next(self, now: float | None = None) -> LiveEvent | None:
        """Highest-priority comment that is still fresh; stale ones are dropped."""
        now = time.monotonic() if now is None else now
        while self._heap:
            item = heapq.heappop(self._heap)
            if now - item.queued_at > self.max_comment_age_seconds:
                self.rejected["stale"] += 1
                continue
            self._viewers_answered_before.add(f"{item.event.platform}:{item.event.viewer_id}")
            return item.event
        return None

    def clear(self) -> None:
        self._heap.clear()

    def __len__(self) -> int:
        return len(self._heap)
