"""Broadcast controller (Module F): runs the live show.

- Receives events from the live source (reconnecting with backoff after errors).
- Sends each event through deduplication, gamification and the comment pipeline.
- Answers the highest-priority comment whenever Sokokali is not already speaking.
  Speaking time is estimated from the reply length so answers never overlap.
- Fills quiet moments with scheduled segments: match preview, trivia, forex
  outlook, fans' poll and a responsible-gambling reminder.
- Publishes everything to the live hub (WebSocket) for the dashboard and avatar.
- Can be started, paused and stopped at any time by an admin (human oversight).
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from app.core.background import spawn
from app.integrations.live.base import LiveEventSource, LiveSourceUnavailableError
from app.schemas.chat import ChatRequest, Language
from app.schemas.live import BroadcastState, BroadcastStatus, LiveEvent, LiveEventKind
from app.schemas.speech import AvatarAnimation, SpeechCue
from app.services.chat_service import ChatService
from app.services.compliance import ComplianceService
from app.services.gamification import LETTERS, GamificationEngine
from app.services.live_hub import LiveHub
from app.services.live_pipeline import LiveEventPipeline
from app.services.speech_service import VOICE_LANGUAGES, speakable_text
from app.services.sports_engine import SportsService

logger = logging.getLogger(__name__)

SEGMENTS = ("match_preview", "trivia", "forex", "poll", "responsible_gambling")
SEGMENT_LANGUAGES = (Language.KISWAHILI, Language.ENGLISH, Language.SHENG)


class BroadcastController:
    def __init__(
        self,
        source: LiveEventSource,
        pipeline: LiveEventPipeline,
        gamification: GamificationEngine,
        chat: ChatService,
        sports: SportsService,
        compliance: ComplianceService,
        hub: LiveHub,
        *,
        forex_enabled: bool = True,
        words_per_second: float = 2.6,
        min_gap_seconds: float = 2.0,
        segment_interval_seconds: float = 45.0,
        segment_max_gap_seconds: float = 180.0,
        trivia_seconds: float = 30.0,
        poll_seconds: float = 45.0,
        tick_seconds: float = 0.25,
        reconnect_max_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
        autoloop: bool = True,
    ) -> None:
        self.source = source
        self.pipeline = pipeline
        self.gamification = gamification
        self.chat = chat
        self.sports = sports
        self.compliance = compliance
        self.hub = hub
        self.forex_enabled = forex_enabled
        self.words_per_second = words_per_second
        self.min_gap_seconds = min_gap_seconds
        self.segment_interval_seconds = segment_interval_seconds
        self.segment_max_gap_seconds = segment_max_gap_seconds
        self.trivia_seconds = trivia_seconds
        self.poll_seconds = poll_seconds
        self.tick_seconds = tick_seconds
        self.reconnect_max_seconds = reconnect_max_seconds
        self.clock = clock
        self.autoloop = autoloop

        self.state = BroadcastState.STOPPED
        self.started_at: datetime | None = None
        self.source_error: str | None = None
        self.speaking_until = 0.0
        self.last_activity = 0.0
        self.last_segment = 0.0
        self.replies = 0
        self.segments = 0
        self.events_received = 0
        self.errors = 0
        self.last_error: str | None = None
        self._segment_index = 0
        self._tasks: list[asyncio.Task[None]] = []
        # Optional hooks (set by the container): storage and metrics.
        self.on_say: Callable[[dict[str, Any]], Awaitable[None]] | None = None
        self.on_gamification_state: Callable[[dict[str, Any]], Awaitable[None]] | None = None
        self.on_event: Callable[[LiveEvent], None] | None = None
        # Which audience feeds the show ("simulated", "relay", "tiktok"); switchable while stopped.
        self.audience = "simulated"
        self.source_factory: Callable[[str], LiveEventSource] | None = None
        self.snapshot_seconds = 30.0
        self._last_snapshot = 0.0

    # -- control ---------------------------------------------------------------

    async def start(self, audience: str | None = None) -> BroadcastStatus:
        """Start (or resume) the show, optionally choosing the audience first.

        Raises LiveSourceUnavailableError if the source cannot run, ValueError if the audience is
        changed while the show is on.
        """
        if audience is not None and audience != self.audience:
            if self.state != BroadcastState.STOPPED:
                raise ValueError("Stop the broadcast before switching the audience")
            if self.source_factory is None:
                raise ValueError("This broadcast cannot switch audience")
            self.source = self.source_factory(audience)
            self.audience = audience
        if self.state == BroadcastState.PAUSED:
            self.state = BroadcastState.RUNNING
            self._publish_state()
            return self.status()
        if self.state == BroadcastState.RUNNING:
            return self.status()
        await self.source.check()
        self.state = BroadcastState.RUNNING
        self.started_at = datetime.now(UTC)
        self.source_error = None
        self.last_activity = self.last_segment = self.clock()
        self._tasks = [asyncio.create_task(self._run_source(), name="live-source")]
        if self.autoloop:
            self._tasks.append(asyncio.create_task(self._run_loop(), name="broadcast-loop"))
            self._tasks.append(asyncio.create_task(self._run_snapshots(), name="gamification-snapshots"))
        logger.info("broadcast_started", extra={"source": self.source.name})
        self._publish_state()
        return self.status()

    async def pause(self) -> BroadcastStatus:
        """Stop talking but keep receiving events (comments keep queueing, up to the queue limit)."""
        if self.state == BroadcastState.RUNNING:
            self.state = BroadcastState.PAUSED
            logger.info("broadcast_paused")
            self._publish_state()
        return self.status()

    async def stop(self) -> BroadcastStatus:
        """Disconnect from the source, drop queued comments and end any trivia or poll."""
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 - shutting down
                pass
        self._tasks = []
        if self.state != BroadcastState.STOPPED:
            logger.info("broadcast_stopped", extra={"replies": self.replies})
        self.state = BroadcastState.STOPPED
        self.started_at = None
        self.speaking_until = 0.0
        self.pipeline.clear()
        self.gamification.close_trivia()
        self.gamification.close_poll()
        await self.save_gamification()
        self._publish_state()
        return self.status()

    async def save_gamification(self) -> None:
        if self.on_gamification_state is not None:
            await self.on_gamification_state(self.gamification.export_state())

    async def _run_snapshots(self) -> None:
        while True:
            await asyncio.sleep(self.snapshot_seconds)
            await self.save_gamification()

    def status(self) -> BroadcastStatus:
        now = self.clock()
        return BroadcastStatus(
            state=self.state,
            source=self.source.name,
            audience=self.audience,
            source_is_simulated=self.source.is_simulated,
            source_error=self.source_error,
            started_at=self.started_at,
            uptime_seconds=(datetime.now(UTC) - self.started_at).total_seconds() if self.started_at else 0.0,
            queue_size=len(self.pipeline),
            replies=self.replies,
            segments=self.segments,
            events_received=self.events_received,
            comments_rejected=dict(self.pipeline.rejected),
            errors=self.errors,
            last_error=self.last_error,
            speaking_until=(
                datetime.fromtimestamp(datetime.now(UTC).timestamp() + self.speaking_until - now, UTC)
                if self.speaking_until > now
                else None
            ),
            connected_clients=self.hub.client_count,
        )

    def _publish_state(self) -> None:
        self.hub.publish("state", self.status().model_dump(mode="json"))

    def _alert(self, message: str) -> None:
        self.errors += 1
        self.last_error = message
        self.hub.publish("alert", {"message": message})

    # -- events ------------------------------------------------------------------

    async def handle_event(self, event: LiveEvent) -> dict[str, Any]:
        """Process one incoming event (from the source, or injected through the API)."""
        self.events_received += 1
        if self.on_event is not None:
            self.on_event(event)
        if self.pipeline.is_duplicate(event):
            self.pipeline.rejected["duplicate"] += 1
            return {"accepted": False, "reason": "duplicate"}
        now = self.clock()
        updates = self.gamification.process(event, now)
        result: dict[str, Any] = {"accepted": False, "reason": None, "priority": None}
        if event.kind == LiveEventKind.COMMENT:
            result = (await self.pipeline.ingest(event, now)).model_dump()
        self.hub.publish("event", {**event.model_dump(mode="json"), **result})
        for update in updates:
            self.hub.publish("game", update.model_dump(mode="json"))
            if update.kind == "milestone":
                spawn(self.save_gamification(), "save_gamification")  # milestones are worth keeping at once
                if self.state == BroadcastState.RUNNING:
                    self._say(update.message, Language.ENGLISH, AvatarAnimation.CELEBRATION, "milestone")
        return result

    async def _run_source(self) -> None:
        backoff = 1.0
        while True:
            try:
                await self.source.run(self.handle_event)
                backoff = 1.0
            except asyncio.CancelledError:
                raise
            except LiveSourceUnavailableError as exc:
                self.source_error = str(exc)
                self._alert(f"Live source unavailable: {exc}")
                return
            except Exception as exc:  # noqa: BLE001 - any connector failure: reconnect
                logger.exception("live_source_failed")
                self._alert(f"Live source error, reconnecting in {backoff:.0f}s: {exc}")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self.reconnect_max_seconds)

    # -- show loop -----------------------------------------------------------------

    async def _run_loop(self) -> None:
        while True:
            await asyncio.sleep(self.tick_seconds)
            try:
                await self.step(self.clock())
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - one bad reply must not end the show
                logger.exception("broadcast_step_failed")
                self._alert(f"Broadcast step failed: {exc}")
                self.speaking_until = self.clock() + self.min_gap_seconds

    async def step(self, now: float) -> None:
        """One iteration of the show: close due rounds, then answer a comment or run a segment."""
        for update in self.gamification.due(now):
            self.hub.publish("game", update.model_dump(mode="json"))
            if self.state == BroadcastState.RUNNING:
                self._say(update.message, Language.ENGLISH, AvatarAnimation.COMMENTARY, update.kind)
        if self.state != BroadcastState.RUNNING or now < self.speaking_until:
            return
        # Segments fill quiet moments, but also interrupt a busy chat now and then, so trivia, polls and the
        # responsible-gambling reminder are never skipped for a whole stream.
        if now - self.last_segment >= self.segment_max_gap_seconds:
            await self._segment(now)
            return
        event = self.pipeline.next(now)
        if event is not None:
            await self._respond(event)
        elif now - self.last_activity >= self.segment_interval_seconds:
            await self._segment(now)

    def _publish_say(self, data: dict[str, Any]) -> None:
        self.hub.publish("say", data)
        if self.on_say is not None:
            spawn(self.on_say(data), "log_broadcast")

    def _speaking(self, text: str) -> None:
        now = self.clock()
        self.speaking_until = now + len(text.split()) / self.words_per_second + self.min_gap_seconds
        self.last_activity = self.speaking_until

    async def _respond(self, event: LiveEvent) -> None:
        response = await self.chat.handle(
            ChatRequest(message=(event.text or "")[:500], viewer_id=f"{event.platform}:{event.viewer_id}")
        )
        self.replies += 1
        self._publish_say(
            {
                "source": "viewer",
                "viewer_name": event.viewer_name,
                "comment": event.text,
                "text": response.reply,
                "speech": response.speech.model_dump(mode="json") if response.speech else None,
                "response": response.model_dump(mode="json"),
            },
        )
        self._speaking(response.speech.text if response.speech else response.reply)

    def _say(self, text: str, language: Language, animation: AvatarAnimation, source: str, simulated: bool = False) -> None:
        cue = SpeechCue(
            text=speakable_text(text, language),
            voice_languages=VOICE_LANGUAGES[language],
            animation=animation,
            show_simulated_banner=simulated,
        )
        self._publish_say({"source": source, "text": text, "speech": cue.model_dump(mode="json")})
        self._speaking(cue.text)

    async def run_segment(self, segment: str) -> None:
        """Run a named segment now (admin trigger), whatever the rotation says."""
        if segment not in SEGMENTS:
            raise ValueError(f"Unknown segment {segment}")
        await self._segment(self.clock(), segment)

    async def _segment(self, now: float, forced: str | None = None) -> None:
        segment = forced or SEGMENTS[self._segment_index % len(SEGMENTS)]
        self.last_segment = now
        language = SEGMENT_LANGUAGES[self._segment_index % len(SEGMENT_LANGUAGES)]
        self._segment_index += 1
        self.segments += 1
        if segment == "forex" and not self.forex_enabled:
            segment = "responsible_gambling"
        if segment in ("trivia", "poll") and (self.gamification.trivia or self.gamification.poll):
            segment = "match_preview"  # one game at a time

        if segment == "responsible_gambling":
            self._say(self.compliance.responsible_gambling_message(language), language, AvatarAnimation.SPEAKING, segment)
            return
        if segment == "trivia":
            q = self.gamification.start_trivia(now, self.trivia_seconds)
            options = " ".join(f"{LETTERS[i]}) {o}." for i, o in enumerate(q.options))
            if language == Language.ENGLISH:
                text = f"Trivia time! {q.question_en} {options} Type the letter in the chat!"
            else:
                text = f"Wakati wa trivia! {q.question_sw} {options} Andika herufi kwenye chat!"
            self._say(text, language, AvatarAnimation.CELEBRATION, segment)
            self.hub.publish("game", {"kind": "trivia_started", "viewer_name": None, "message": text, "data": {}})
            return

        fixtures = await self.sports.upcoming_fixtures(limit=5)
        fixture = fixtures[self.segments % len(fixtures)] if fixtures else None
        if segment == "poll" and fixture:
            home, away = fixture.home_team.name, fixture.away_team.name
            self.gamification.start_poll(fixture.match_id, home, away, now, self.poll_seconds)
            if language == Language.ENGLISH:
                text = f"Fans' poll! {home} vs {away}: type 1 for {home}, X for a draw, or 2 for {away}."
            else:
                text = f"Kura ya mashabiki! {home} dhidi ya {away}: andika 1 kwa {home}, X kwa sare, au 2 kwa {away}."
            self._say(text, language, AvatarAnimation.COMMENTARY, segment)
            self.hub.publish("game", {"kind": "poll_started", "viewer_name": None, "message": text, "data": {}})
            return

        if segment == "forex":
            message = {Language.ENGLISH: "Forex outlook please", Language.KISWAHILI: "Nipe uchambuzi wa forex"}.get(
                language, "Forex signals za leo?"
            )
        elif fixture:
            message = f"{fixture.home_team.name} vs {fixture.away_team.name} who will win?"
        else:
            message = "What are the upcoming fixtures?"
        response = await self.chat.handle(ChatRequest(message=message, language=language))
        self._publish_say(
            {
                "source": segment,
                "text": response.reply,
                "speech": response.speech.model_dump(mode="json") if response.speech else None,
                "response": response.model_dump(mode="json"),
            },
        )
        self._speaking(response.speech.text if response.speech else response.reply)

