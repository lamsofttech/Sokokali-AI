"""Phase 7: persistence (SQLite stands in for PostgreSQL), Redis fallback, metrics and readiness."""

import asyncio
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from pydantic import SecretStr
from redis.asyncio import Redis

from app.core.background import drain
from app.core.config import Settings
from app.core.container import build_container
from app.core.rate_limit import RedisRateLimiter
from app.main import create_app
from app.schemas.live import LiveEvent, LiveEventKind
from tests.test_live import IdleSource


def _settings(settings: Settings, tmp_path: Path, **extra: Any) -> Settings:
    url = f"sqlite+aiosqlite:///{(tmp_path / 'sokokali.db').as_posix()}"
    return settings.model_copy(update={"database_url": SecretStr(url), **extra})


def _client(s: Settings, provider: Any, forex_provider: Any) -> TestClient:
    container = build_container(s, sports_provider=provider, forex_provider=forex_provider, live_source=IdleSource())
    return TestClient(create_app(s, container))


def test_predictions_are_stored_once_per_distinct_result(
    settings: Settings, provider: Any, forex_provider: Any, tmp_path: Path
) -> None:
    s = _settings(settings, tmp_path)
    with _client(s, provider, forex_provider) as client:
        match_id = client.get("/api/v1/fixtures").json()["fixtures"][0]["match_id"]
        for _ in range(3):  # the dashboard polls; identical predictions are stored once
            assert client.get(f"/api/v1/predictions/{match_id}").status_code == 200
        client.post("/api/v1/chat", json={"message": "Arsenal vs Chelsea who will win?"})
        client.portal.call(drain)  # type: ignore[union-attr]
        history = client.get("/api/v1/history/predictions").json()
    assert len(history) == 1
    assert history[0]["match_id"] == match_id and history[0]["model_version"] == s.prediction_model_version
    assert history[0]["is_simulated"] is True


def test_broadcast_log_and_gamification_survive_restart(
    settings: Settings, provider: Any, forex_provider: Any, tmp_path: Path
) -> None:
    s = _settings(settings, tmp_path)
    like = {"event_id": "l1", "platform": "test", "viewer_id": "fan", "viewer_name": "Fan", "kind": "like", "count": 150}
    with _client(s, provider, forex_provider) as client:
        client.post("/api/v1/broadcast/start")
        assert client.post("/api/v1/live/events", json=like).status_code == 200
        client.post("/api/v1/broadcast/segments/responsible_gambling")
        client.post("/api/v1/broadcast/stop")  # saves the gamification snapshot
        client.portal.call(drain)  # let background log writes finish  # type: ignore[union-attr]
        said = client.get("/api/v1/history/broadcast").json()
    assert any(row["source"] == "responsible_gambling" for row in said)
    assert any(row["source"] == "milestone" for row in said)

    with _client(s, provider, forex_provider) as client:  # a fresh process, same database
        status = client.get("/api/v1/gamification/status").json()
    assert status["totals"]["likes"] == 150
    assert status["background"] == "floodlights"
    assert any(m["id"] == "likes-100" and m["reached"] for m in status["milestones"])


def test_readiness_and_status_report_database(
    settings: Settings, provider: Any, forex_provider: Any, tmp_path: Path
) -> None:
    with _client(_settings(settings, tmp_path), provider, forex_provider) as client:
        assert client.get("/ready").json()["checks"]["database"] is True
        components = {c["name"]: c for c in client.get("/api/v1/status").json()["components"]}
    assert components["database"]["status"] == "ok"
    assert components["redis"]["status"] == "disabled"


def test_history_without_database_is_503(client: TestClient) -> None:
    assert client.get("/api/v1/history/predictions").status_code == 503


def test_unreachable_database_falls_back_to_memory(settings: Settings, provider: Any, forex_provider: Any) -> None:
    s = settings.model_copy(update={"database_url": SecretStr("sqlite+aiosqlite:////no/such/dir/x.db")})
    container = build_container(s, sports_provider=provider, forex_provider=forex_provider, live_source=IdleSource())

    async def fast_sleep(_: float) -> None:
        return None

    original = asyncio.sleep
    asyncio.sleep = fast_sleep  # type: ignore[assignment]
    try:
        asyncio.run(container.startup())
    finally:
        asyncio.sleep = original  # type: ignore[assignment]
    assert container.storage is None and container.predictions.on_prediction is None


def test_redis_rate_limiter_falls_back_when_redis_is_down() -> None:
    redis = Redis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.2, socket_timeout=0.2)
    limiter = RedisRateLimiter(redis, limit=2)

    async def run() -> list[bool]:
        try:
            return [await limiter.check("client") for _ in range(3)]
        finally:
            await redis.aclose()

    assert asyncio.run(run()) == [True, True, False]


def test_metrics_endpoint(client: TestClient, container: Any) -> None:
    client.get("/health")
    client.post("/api/v1/chat", json={"message": "Habari"})
    asyncio.run(
        container.broadcast.handle_event(
            LiveEvent(event_id="m1", platform="test", viewer_id="v", viewer_name="V", kind=LiveEventKind.JOIN)
        )
    )
    text = client.get("/metrics").text
    assert 'sokokali_http_requests_total{method="GET",route="/health",status="200"}' in text
    assert 'sokokali_chat_replies_total{engine="rules",intent="greeting"}' in text
    assert 'sokokali_live_events_total{kind="join"}' in text
    assert "sokokali_live_queue_size 0.0" in text


def test_metrics_need_admin_token_when_configured(settings: Settings, provider: Any, forex_provider: Any) -> None:
    s = settings.model_copy(update={"admin_token": SecretStr("tok")})
    with _client(s, provider, forex_provider) as client:
        assert client.get("/metrics").status_code == 401
        assert client.get("/metrics", headers={"Authorization": "Bearer tok"}).status_code == 200
