"""Phase 6: live pipeline, gamification, broadcast controller, admin auth and the live WebSocket."""

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import Settings
from app.core.container import Container, build_container
from app.integrations.live.base import EventCallback, LiveEventSource, LiveSourceUnavailableError
from app.integrations.live.simulated import SimulatedLiveSource, Topics
from app.integrations.live.tiktok import TikTokLiveSource
from app.main import create_app
from app.schemas.live import BroadcastState, LiveEvent, LiveEventKind
from app.services.gamification import POINTS_POLL_VOTE, POINTS_TRIVIA_CORRECT, POINTS_TRIVIA_FIRST, TRIVIA, GamificationEngine

_seq = 0


def ev(kind: LiveEventKind = LiveEventKind.COMMENT, text: str | None = None, viewer: str = "v1", **kw: Any) -> LiveEvent:
    global _seq
    _seq += 1
    return LiveEvent(
        event_id=kw.pop("event_id", f"e{_seq}"),
        platform="test",
        viewer_id=viewer,
        viewer_name=kw.pop("name", viewer.upper()),
        kind=kind,
        text=text,
        **kw,
    )


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


class IdleSource(LiveEventSource):
    """Connects and then waits; tests push events through handle_event directly."""

    name = "test"
    is_simulated = True

    async def run(self, emit: EventCallback) -> None:
        await asyncio.Event().wait()


class CrashingSource(LiveEventSource):
    name = "crashy"
    is_simulated = False

    def __init__(self) -> None:
        self.runs = 0

    async def run(self, emit: EventCallback) -> None:
        self.runs += 1
        raise ConnectionError("platform dropped the connection")


@pytest.fixture
def live(settings: Settings, provider: Any, forex_provider: Any) -> tuple[Container, Clock]:
    container = build_container(
        settings, sports_provider=provider, forex_provider=forex_provider, live_source=IdleSource(), autoloop=False
    )
    clock = Clock()
    container.broadcast.clock = clock
    return container, clock


# --- pipeline ---------------------------------------------------------------------


def test_pipeline_filters(live: tuple[Container, Clock]) -> None:
    container, _ = live
    pipeline = container.broadcast.pipeline

    async def run() -> dict[str, Any]:
        out = {}
        first = ev(text="Arsenal vs Chelsea who will win?")
        out["dup_id"] = (pipeline.is_duplicate(first, 0), pipeline.is_duplicate(first, 1))
        out["ok"] = (await pipeline.ingest(first, 0)).accepted
        out["repeat"] = (await pipeline.ingest(ev(text="arsenal  vs chelsea who will WIN?"), 1)).reason
        out["short"] = (await pipeline.ingest(ev(text="A"), 2)).reason
        out["moderated"] = (await pipeline.ingest(ev(text="Call me 0712345678", viewer="v2"), 3)).reason
        out["not_comment"] = (await pipeline.ingest(ev(LiveEventKind.LIKE), 4)).reason
        for i in range(4):  # the limit is 4 comments per viewer per minute
            await pipeline.ingest(ev(text=f"question number {i} please", viewer="v3"), 5)
        out["rate"] = (await pipeline.ingest(ev(text="one more question", viewer="v3"), 6)).reason
        out["rate_later"] = (await pipeline.ingest(ev(text="a later question", viewer="v3"), 70)).accepted
        return out

    out = asyncio.run(run())
    assert out["dup_id"] == (False, True)
    assert out["ok"] is True
    assert out["repeat"] == "repeated_comment"
    assert out["short"] == "too_short"
    assert out["moderated"] == "moderated"
    assert out["not_comment"] == "not_a_comment"
    assert out["rate"] == "rate_limited" and out["rate_later"] is True


def test_pipeline_priority_and_staleness(live: tuple[Container, Clock]) -> None:
    pipeline = live[0].broadcast.pipeline

    async def run() -> list[str]:
        await pipeline.ingest(ev(text="Habari Sokokali", viewer="a"), 0)
        await pipeline.ingest(ev(text="Gor Mahia vs AFC Leopards nani atashinda?", viewer="b"), 0)
        await pipeline.ingest(ev(text="EUR/USD signal?", viewer="c"), 0)
        first = pipeline.next(1)
        second = pipeline.next(1)
        await pipeline.ingest(ev(text="an old question here", viewer="d"), 0)
        stale = pipeline.next(1000)  # older than max_comment_age: dropped
        return [first.text if first else "", second.text if second else "", str(stale)]

    first, second, stale = asyncio.run(run())
    assert "Gor Mahia" in first or "EUR/USD" in first
    assert "Habari" not in first and "Habari" not in second  # greetings wait behind real questions
    assert stale == "None" or "Habari" in stale  # the greeting may still be fresh; the old question is gone
    assert pipeline.rejected["stale"] >= 1


def test_pipeline_queue_limit_drops_lowest(live: tuple[Container, Clock]) -> None:
    pipeline = live[0].broadcast.pipeline
    pipeline.max_queue = 2

    async def run() -> None:
        await pipeline.ingest(ev(text="Habari wasee", viewer="a"), 0)
        await pipeline.ingest(ev(text="Arsenal vs Chelsea who wins?", viewer="b"), 0)
        await pipeline.ingest(ev(text="Liverpool vs Manchester City who wins?", viewer="c"), 0)

    asyncio.run(run())
    assert len(pipeline) == 2
    assert pipeline.rejected["queue_full"] == 1
    remaining = [pipeline.next(0), pipeline.next(0)]
    assert all("Habari" not in (e.text or "") for e in remaining if e)


# --- gamification -------------------------------------------------------------------


def test_milestones_unlock_cosmetics() -> None:
    game = GamificationEngine(seed=1)
    updates = game.process(ev(LiveEventKind.LIKE, count=150), 0)
    assert any(u.kind == "milestone" and u.data["background"] == "floodlights" for u in updates)
    game.process(ev(LiveEventKind.LIKE, count=400), 1)
    assert game.outfit == "away"
    assert game.process(ev(LiveEventKind.LIKE, count=1), 2) == []  # each milestone fires once


def test_gifts_are_cosmetic_only() -> None:
    game = GamificationEngine()
    updates = game.process(ev(LiveEventKind.GIFT, viewer="rich", gift_name="Trophy"), 0)
    assert updates[0].kind == "gift" and updates[0].data["effect"] == "confetti"
    assert game.points["test:rich"] == 0
    assert "Gifts are cosmetic only" in game.status().rules


def test_trivia_scoring() -> None:
    game = GamificationEngine(seed=3)
    q = game.start_trivia(now=0, duration_seconds=30)
    right = "abcd"[q.answer]
    wrong = "abcd"[(q.answer + 1) % 4]
    game.process(ev(text=wrong, viewer="w"), 1)
    game.process(ev(text=right, viewer="w"), 2)  # second answer ignored
    game.process(ev(text=f"jibu ni {right}", viewer="x"), 3)
    game.process(ev(text=right.upper() + "!", viewer="y"), 4)
    game.process(ev(text="I think the answer is a", viewer="z"), 5)  # sentences are not answers
    assert game.status().trivia is not None and game.status().trivia.winners == ["X", "Y"]
    assert game.points["test:x"] == POINTS_TRIVIA_FIRST + 1 and game.points["test:y"] == POINTS_TRIVIA_CORRECT + 1
    assert game.points["test:w"] == 1  # comment point only
    closed = game.due(31)
    assert closed[0].kind == "trivia_closed" and "X" in closed[0].message
    assert game.trivia is None
    assert q in TRIVIA


def test_poll_votes_and_tally() -> None:
    game = GamificationEngine()
    game.start_poll("m1", "Arsenal", "Chelsea", now=0, duration_seconds=45)
    for viewer, vote in [("a", "1"), ("b", "x"), ("c", "2"), ("d", "chelsea"), ("a", "2")]:
        game.process(ev(text=vote, viewer=viewer), 1)
    assert game.status().poll is not None and game.status().poll.votes == {"home": 1, "draw": 1, "away": 2}
    result = game.close_poll()
    assert result is not None and "not a prediction" in result.message
    assert game.points["test:a"] == POINTS_POLL_VOTE + 1


def test_comment_points_capped_per_minute() -> None:
    game = GamificationEngine()
    for t in (0, 10, 20, 70):
        game.process(ev(text="hello there", viewer="fan"), t)
    assert game.points["test:fan"] == 2
    assert game.status().leaderboard[0].viewer_name == "FAN"


# --- simulated source --------------------------------------------------------------


def test_simulated_source_events_are_valid_and_varied() -> None:
    source = SimulatedLiveSource(lambda: None, seed=7)  # type: ignore[arg-type,return-value]
    topics = Topics(matches=[("Arsenal", "Chelsea")], pairs=["EUR/USD"])
    events = [source.next_event(topics) for _ in range(400)]
    kinds = {e.kind for e in events}
    assert {LiveEventKind.JOIN, LiveEventKind.COMMENT, LiveEventKind.LIKE, LiveEventKind.GIFT} <= kinds
    assert all(e.is_simulated and e.platform == "simulated" for e in events)
    texts = " ".join(e.text or "" for e in events)
    assert "Arsenal" in texts and "EUR/USD" in texts
    assert len({e.event_id for e in events}) < len(events)  # occasional duplicate deliveries


# --- broadcast controller ----------------------------------------------------------


def test_controller_answers_one_comment_at_a_time(live: tuple[Container, Clock]) -> None:
    container, clock = live
    bc = container.broadcast
    queue = container.hub.connect()

    async def run() -> None:
        await bc.start()
        await bc.handle_event(ev(text="Arsenal vs Chelsea who will win?", viewer="a"))
        await bc.handle_event(ev(text="EUR/USD signal please?", viewer="b"))
        await bc.step(clock.t)
        assert bc.replies == 1
        await bc.step(clock.t + 1)  # still speaking
        assert bc.replies == 1
        clock.t = bc.speaking_until + 0.1
        await bc.step(clock.t)
        assert bc.replies == 2
        await bc.stop()

    asyncio.run(run())
    messages = []
    while not queue.empty():
        messages.append(queue.get_nowait())
    says = [m for m in messages if m["type"] == "say"]
    assert len(says) == 2 and says[0]["data"]["viewer_name"] == "A"
    assert says[0]["data"]["speech"]["animation"] == "commentary"
    assert any(m["type"] == "event" and m["data"]["accepted"] for m in messages)
    assert bc.state == BroadcastState.STOPPED


def test_controller_runs_segments_when_quiet(live: tuple[Container, Clock]) -> None:
    container, clock = live
    bc = container.broadcast
    queue = container.hub.connect()

    async def run() -> list[str]:
        await bc.start()
        sources = []
        for _ in range(10):  # some steps are used to announce trivia/poll results
            if bc.segments == 5:
                break
            clock.t = max(clock.t, bc.speaking_until) + bc.segment_interval_seconds + 1
            await bc.step(clock.t)
        while not queue.empty():
            m = queue.get_nowait()
            if m["type"] == "say" and not m["data"]["source"].endswith("_closed"):
                sources.append(m["data"]["source"])  # (trivia/poll results are announced in between)
        await bc.stop()
        return sources

    sources = asyncio.run(run())
    assert sources[:5] == ["match_preview", "trivia", "forex", "poll", "responsible_gambling"]
    assert bc.segments == 5


def test_pause_keeps_queueing_but_stops_talking(live: tuple[Container, Clock]) -> None:
    container, clock = live
    bc = container.broadcast

    async def run() -> None:
        await bc.start()
        await bc.pause()
        await bc.handle_event(ev(text="Liverpool form please?", viewer="p"))
        await bc.step(clock.t + 5)
        assert bc.replies == 0 and len(bc.pipeline) == 1
        await bc.start()  # resume
        assert bc.state == BroadcastState.RUNNING
        await bc.step(clock.t + 10)
        assert bc.replies == 1
        await bc.stop()

    asyncio.run(run())


def test_source_crash_is_retried_with_alerts(settings: Settings, provider: Any, forex_provider: Any) -> None:
    source = CrashingSource()
    container = build_container(
        settings, sports_provider=provider, forex_provider=forex_provider, live_source=source, autoloop=False
    )

    async def run() -> None:
        await container.broadcast.start()
        await asyncio.sleep(1.2)  # first retry after 1 s
        await container.broadcast.stop()

    asyncio.run(run())
    assert source.runs >= 2
    assert container.broadcast.errors >= 2 and "reconnecting" in (container.broadcast.last_error or "")


def test_tiktok_refuses_to_start() -> None:
    with pytest.raises(LiveSourceUnavailableError, match="authorized"):
        asyncio.run(TikTokLiveSource().check())


# --- API, auth and WebSocket ------------------------------------------------------------


def _app(settings: Settings, provider: Any, forex_provider: Any, **overrides: Any) -> TestClient:
    s = settings.model_copy(update=overrides)
    container = build_container(s, sports_provider=provider, forex_provider=forex_provider, live_source=IdleSource())
    return TestClient(create_app(s, container))


def test_admin_endpoints_need_token_when_configured(settings: Settings, provider: Any, forex_provider: Any) -> None:
    with _app(settings, provider, forex_provider, admin_token=SecretStr("s3cret")) as client:
        assert client.post("/api/v1/broadcast/start").status_code == 401
        assert client.post("/api/v1/broadcast/start", headers={"Authorization": "Bearer wrong"}).status_code == 401
        ok = client.post("/api/v1/broadcast/start", headers={"Authorization": "Bearer s3cret"})
        assert ok.status_code == 200 and ok.json()["state"] == "running"
        assert client.get("/api/v1/broadcast/status").json()["state"] == "running"  # status is public
        assert client.post("/api/v1/broadcast/stop", headers={"Authorization": "Bearer s3cret"}).json()["state"] == "stopped"


def test_production_without_token_fails_closed(settings: Settings, provider: Any, forex_provider: Any) -> None:
    with _app(settings, provider, forex_provider, environment="production") as client:
        assert client.post("/api/v1/broadcast/start").status_code == 503


def test_blank_admin_token_means_unset() -> None:
    assert Settings(admin_token="  ", _env_file=None).admin_token is None


def test_tiktok_source_start_returns_409(settings: Settings, provider: Any, forex_provider: Any) -> None:
    s = settings.model_copy(update={"live_source": "tiktok"})
    with TestClient(create_app(s, build_container(s, sports_provider=provider, forex_provider=forex_provider))) as client:
        res = client.post("/api/v1/broadcast/start")
        assert res.status_code == 409 and "authorized" in res.json()["detail"]


def test_websocket_feed(settings: Settings, provider: Any, forex_provider: Any) -> None:
    with _app(settings, provider, forex_provider, admin_token=SecretStr("tok")) as client:
        with pytest.raises(Exception):
            with client.websocket_connect("/ws/live") as ws:
                ws.receive_json()
        with client.websocket_connect("/ws/live?token=tok") as ws:
            snapshot = ws.receive_json()
            assert snapshot["type"] == "snapshot" and snapshot["data"]["state"]["state"] == "stopped"
            body = {
                "event_id": "x1",
                "platform": "test",
                "viewer_id": "v9",
                "viewer_name": "Zawadi",
                "kind": "gift",
                "gift_name": "Rose",
            }
            res = client.post("/api/v1/live/events", json=body, headers={"Authorization": "Bearer tok"})
            assert res.status_code == 200
            first = ws.receive_json()
            assert first["type"] == "event" and first["data"]["viewer_name"] == "Zawadi"
            game = ws.receive_json()
            assert game["type"] == "game" and game["data"]["data"]["effect"] == "confetti"


def test_gamification_and_segment_endpoints(client: TestClient) -> None:
    assert client.post("/api/v1/broadcast/segments/trivia").json() == {"started": "trivia"}
    status = client.get("/api/v1/gamification/status").json()
    assert status["trivia"]["options"][0].startswith("A)")
    assert client.post("/api/v1/broadcast/segments/nope").status_code == 422
    components = {c["name"]: c for c in client.get("/api/v1/status").json()["components"]}
    assert components["broadcast"]["status"] == "stopped"


def test_segments_still_run_when_chat_is_busy(live: tuple[Container, Clock]) -> None:
    container, clock = live
    bc = container.broadcast

    async def run() -> None:
        await bc.start()
        for i in range(5):
            await bc.handle_event(ev(text=f"Arsenal vs Chelsea who wins, take {i}?", viewer=f"busy{i}"))
        bc.last_segment = clock.t - bc.segment_max_gap_seconds - 1  # no segment for 3 minutes
        await bc.step(clock.t)
        assert bc.segments == 1 and bc.replies == 0  # the segment goes first
        clock.t = bc.speaking_until + 0.1
        await bc.step(clock.t)
        assert bc.replies == 1  # then back to answering viewers
        await bc.stop()

    asyncio.run(run())


def test_trivia_answers_are_not_queued_as_questions(live: tuple[Container, Clock]) -> None:
    pipeline = live[0].broadcast.pipeline
    result = asyncio.run(pipeline.ingest(ev(text="jibu ni B", viewer="t"), 0))
    assert result.reason == "game_answer" and len(pipeline) == 0


# --- moderator relay (real TikTok comments typed in by a person) --------------------------


def test_relay_audience_end_to_end(settings: Settings, provider: Any, forex_provider: Any) -> None:
    container = build_container(settings, sports_provider=provider, forex_provider=forex_provider)
    with TestClient(create_app(settings, container)) as client:
        started = client.post("/api/v1/broadcast/start", params={"audience": "relay"}).json()
        assert started["audience"] == "relay" and started["source"] == "tiktok-relay"
        assert started["source_is_simulated"] is False

        res = client.post("/api/v1/live/relay", json={"viewer_name": "@Wanjiku_254", "text": "Arsenal vs Chelsea nani atashinda?"})
        body = res.json()
        assert res.status_code == 200 and body["accepted"] is True and body["priority"] >= 40
        again = client.post("/api/v1/live/relay", json={"viewer_name": "wanjiku_254", "text": "Arsenal vs Chelsea nani atashinda?"})
        assert again.json()["reason"] == "repeated_comment"  # same viewer (case and @ ignored), same text

        gift = client.post("/api/v1/live/relay", json={"viewer_name": "musa", "kind": "gift", "gift_name": "Rose"})
        assert gift.status_code == 200
        assert client.post("/api/v1/live/relay", json={"viewer_name": "x", "kind": "comment"}).status_code == 422

        # Switching audience while on air is refused; after stopping it works.
        assert client.post("/api/v1/broadcast/start", params={"audience": "simulated"}).status_code == 409
        client.post("/api/v1/broadcast/stop")
        assert client.post("/api/v1/broadcast/start", params={"audience": "simulated"}).json()["audience"] == "simulated"
        client.post("/api/v1/broadcast/stop")
        assert container.gamification.totals["gifts"] == 1


def test_relay_needs_admin_token_when_configured(settings: Settings, provider: Any, forex_provider: Any) -> None:
    with _app(settings, provider, forex_provider, admin_token=SecretStr("tok")) as client:
        assert client.post("/api/v1/live/relay", json={"viewer_name": "a", "text": "hello there"}).status_code == 401
