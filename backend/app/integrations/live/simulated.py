"""A simulated livestream audience for local development.

Viewers join, ask about real fixtures and currency pairs (taken from the
configured data providers), chat in English, Kiswahili and Sheng, answer
trivia and polls, like and send gifts. Some comments are deliberately
problematic (duplicates, spam, personal data, "sure bet" requests) so the
pipeline's filters can be seen working. Every event is marked ``is_simulated``.
"""

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from app.integrations.live.base import EventCallback, LiveEventSource
from app.schemas.live import LiveEvent, LiveEventKind


@dataclass(frozen=True)
class Topics:
    matches: list[tuple[str, str]] = field(default_factory=list)
    pairs: list[str] = field(default_factory=list)


TopicProvider = Callable[[], Awaitable[Topics]]

_VIEWERS = [
    "Wanjiku_K", "OtienoFan", "Brian254", "Achieng", "MusaKE", "Njeri_Gunners", "KevoTheKing", "Amina_Ingwe",
    "Kamau_Reds", "Wairimu", "Ochieng_Kogalo", "Faith_M", "DanTheBanker", "Zawadi", "Mutua254", "Halima_FX",
]

_MATCH_QUESTIONS = [
    "{a} vs {b} who will win?",
    "Sokokali, {a} na {b} nani atashinda?",
    "Niaje msee! {a} vs {b} nani atawin?",
    "When does {a} play next?",
    "{a} form iko aje?",
    "Last time {a} played {b}, what was the score?",
]
_FOREX_QUESTIONS = ["{pair} signal please", "Nipe uchambuzi wa {pair}", "{pair} iko aje leo?"]
_GENERAL = [
    "What are the upcoming fixtures?",
    "Ratiba ya wikendi ni gani?",
    "Habari Sokokali!",
    "Niaje wasee",
    "Hello from Nairobi!",
    "Mambo! Sokokali uko fiti leo",
    "Greetings from Mombasa",
]
_ANSWERS = ["A", "B", "C", "D", "jibu ni B", "C!", "1", "X", "2"]
_PROBLEMS = ["Nipe sure bet ya leo", "Call me on 0712345678 for tips", "Give me a fixed match"]
_GIFTS = ["Rose", "Heart", "Football", "Trophy"]


class SimulatedLiveSource(LiveEventSource):
    name = "simulated"
    is_simulated = True

    def __init__(
        self,
        topics: TopicProvider,
        events_per_second: float = 0.6,
        seed: int | None = None,
    ) -> None:
        self._topics = topics
        self.events_per_second = events_per_second
        self._rng = random.Random(seed)
        self._seq = 0
        self._present: list[int] = []
        self._last: LiveEvent | None = None

    def _viewer(self, index: int) -> tuple[str, str]:
        return f"sim-{index:04d}", _VIEWERS[index % len(_VIEWERS)]

    def _event(self, kind: LiveEventKind, viewer: int, **kwargs: object) -> LiveEvent:
        self._seq += 1
        viewer_id, name = self._viewer(viewer)
        return LiveEvent(
            event_id=f"sim-{self._seq}",
            platform="simulated",
            viewer_id=viewer_id,
            viewer_name=name,
            kind=kind,
            is_simulated=True,
            **kwargs,  # type: ignore[arg-type]
        )

    def _comment_text(self, topics: Topics) -> str:
        roll = self._rng.random()
        if roll < 0.45 and topics.matches:
            a, b = self._rng.choice(topics.matches)
            return self._rng.choice(_MATCH_QUESTIONS).format(a=a, b=b)
        if roll < 0.6 and topics.pairs:
            return self._rng.choice(_FOREX_QUESTIONS).format(pair=self._rng.choice(topics.pairs))
        if roll < 0.82:
            return self._rng.choice(_GENERAL)
        if roll < 0.95:
            return self._rng.choice(_ANSWERS)
        return self._rng.choice(_PROBLEMS)

    def next_event(self, topics: Topics) -> LiveEvent:
        """One random event; public so tests can drive the generator without waiting."""
        if self._last is not None and self._rng.random() < 0.03:
            return self._last  # platforms sometimes deliver the same event twice
        if not self._present or self._rng.random() < 0.18:
            viewer = len(self._present) if self._rng.random() < 0.8 else self._rng.randrange(64)
            if viewer not in self._present:
                self._present.append(viewer)
            event = self._event(LiveEventKind.JOIN, viewer)
        else:
            viewer = self._rng.choice(self._present)
            roll = self._rng.random()
            if roll < 0.62:
                event = self._event(LiveEventKind.COMMENT, viewer, text=self._comment_text(topics))
            elif roll < 0.88:
                event = self._event(LiveEventKind.LIKE, viewer, count=self._rng.randint(1, 25))
            elif roll < 0.94:
                event = self._event(LiveEventKind.GIFT, viewer, gift_name=self._rng.choice(_GIFTS))
            elif roll < 0.98:
                event = self._event(LiveEventKind.FOLLOW, viewer)
            else:
                event = self._event(LiveEventKind.SHARE, viewer)
        self._last = event
        return event

    async def run(self, emit: EventCallback) -> None:
        topics = await self._topics()
        refreshed = 0
        while True:
            await asyncio.sleep(self._rng.expovariate(self.events_per_second))
            refreshed += 1
            if refreshed % 100 == 0:  # pick up new fixtures now and then
                topics = await self._topics()
            await emit(self.next_event(topics))
