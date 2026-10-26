"""Phase 3: real-data provider (mocked HTTP), retries, caching and backtesting."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.container import build_container, build_sports_provider
from app.core.http import UpstreamError, get_json
from app.integrations.sports.base import SportsDataError
from app.integrations.sports.football_data import FootballDataProvider
from app.main import create_app
from app.schemas.sports import MatchResult, MatchStatus, Team
from app.services import backtest as backtest_module
from app.services.backtest import backtest
from app.services.prediction_engine import PredictionEngine, fit_model

# --- football-data.org payloads ------------------------------------------------

ARSENAL = {"id": 57, "name": "Arsenal FC", "shortName": "Arsenal", "tla": "ARS"}
CHELSEA = {"id": 61, "name": "Chelsea FC", "shortName": "Chelsea", "tla": "CHE"}
SPURS = {"id": 73, "name": "Tottenham Hotspur FC", "shortName": "Tottenham", "tla": "TOT"}
COMPETITION = {"id": 2021, "name": "Premier League", "code": "PL"}


def _match(match_id: int, home: dict, away: dict, day: int, status: str, score: tuple | None = None) -> dict:
    return {
        "id": match_id,
        "utcDate": (datetime(2026, 9, 1, 15, tzinfo=UTC) + timedelta(days=day)).isoformat().replace("+00:00", "Z"),
        "status": status,
        "competition": COMPETITION,
        "season": {"startDate": "2026-08-15"},
        "homeTeam": home,
        "awayTeam": away,
        "score": {"fullTime": {"home": score[0], "away": score[1]} if score else {"home": None, "away": None}},
    }


CURRENT = {
    "filters": {"season": "2026"},
    "matches": [
        _match(1, ARSENAL, CHELSEA, 0, "FINISHED", (2, 1)),
        _match(2, CHELSEA, SPURS, 7, "FINISHED", (1, 1)),
        _match(3, SPURS, ARSENAL, 14, "FINISHED", (0, 3)),
        _match(4, ARSENAL, SPURS, 70, "TIMED"),
        _match(5, CHELSEA, ARSENAL, 60, "IN_PLAY"),
        _match(6, {"id": None, "name": None}, SPURS, 80, "SCHEDULED"),  # undecided team: skipped
        _match(7, SPURS, CHELSEA, 21, "POSTPONED"),
    ],
}
PREVIOUS = {"filters": {"season": "2025"}, "matches": [_match(100, CHELSEA, ARSENAL, -300, "FINISHED", (0, 0))]}


class FakeApi:
    """httpx MockTransport handler that records requests and can fail on demand."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.fail_with: int | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.fail_with:
            return httpx.Response(self.fail_with, json={"message": "error"})
        if request.headers.get("X-Auth-Token") != "test-key":
            return httpx.Response(403, json={"message": "bad token"})
        body = PREVIOUS if request.url.params.get("season") == "2025" else CURRENT
        return httpx.Response(200, json=body)


def _provider(api: FakeApi, ttl: float = 300) -> FootballDataProvider:
    return FootballDataProvider(
        api_key="test-key",
        competitions=["pl"],
        base_url="https://api.test/v4",
        cache_ttl_seconds=ttl,
        max_attempts=1,
        client=httpx.AsyncClient(transport=httpx.MockTransport(api)),
    )


def test_football_data_parses_results_and_fixtures() -> None:
    api = FakeApi()
    provider = _provider(api)

    results = asyncio.run(provider.get_results())
    fixtures = asyncio.run(provider.get_fixtures())

    assert [r.match_id for r in results] == ["fd-100", "fd-1", "fd-2", "fd-3"]  # previous season first, sorted
    assert (results[1].home_team.name, results[1].home_goals, results[1].away_goals) == ("Arsenal", 2, 1)
    assert [f.match_id for f in fixtures] == ["fd-5", "fd-4"]
    assert fixtures[0].status == MatchStatus.LIVE
    assert provider.is_simulated is False
    urls = [str(r.url) for r in api.requests]
    assert urls == ["https://api.test/v4/competitions/PL/matches", "https://api.test/v4/competitions/PL/matches?season=2025"]


def test_football_data_team_aliases_skip_three_letter_codes() -> None:
    teams = {t.name: t for t in asyncio.run(_provider(FakeApi()).list_teams())}
    assert "arsenal fc" in teams["Arsenal"].aliases and "arsenal" in teams["Arsenal"].aliases
    assert all(len(a) >= 4 for t in teams.values() for a in t.aliases)  # no "tot", "che"


def test_football_data_caches_until_ttl() -> None:
    api = FakeApi()
    provider = _provider(api)

    async def twice() -> None:
        await provider.get_results()
        await provider.get_fixtures()

    asyncio.run(twice())
    assert len(api.requests) == 2  # one refresh = current + previous season, then served from cache


def test_football_data_serves_stale_snapshot_on_failure() -> None:
    api = FakeApi()
    provider = _provider(api, ttl=0)  # every call tries to refresh

    async def scenario() -> tuple[int, int]:
        first = await provider.get_results()
        api.fail_with = 503
        second = await provider.get_results()
        return len(first), len(second)

    assert asyncio.run(scenario()) == (4, 4)
    assert provider.last_error is not None and "503" in provider.last_error


def test_football_data_raises_without_any_snapshot() -> None:
    api = FakeApi()
    api.fail_with = 500
    provider = _provider(api)
    with pytest.raises(SportsDataError):
        asyncio.run(provider.get_results())
    assert asyncio.run(provider.health_check()) is False


def test_bad_api_key_is_not_retried() -> None:
    api = FakeApi()
    provider = FootballDataProvider(
        api_key="wrong",
        competitions=["PL"],
        base_url="https://api.test/v4",
        max_attempts=3,
        client=httpx.AsyncClient(transport=httpx.MockTransport(api)),
    )
    with pytest.raises(SportsDataError):
        asyncio.run(provider.get_results())
    assert len(api.requests) == 1


def test_provider_requires_key(settings: Settings) -> None:
    misconfigured = settings.model_copy(update={"sports_provider": "football_data", "football_data_api_key": None})
    with pytest.raises(ValueError, match="FOOTBALL_DATA_API_KEY"):
        build_sports_provider(misconfigured)


def test_real_provider_prediction_end_to_end(settings: Settings) -> None:
    provider = _provider(FakeApi())
    engine = PredictionEngine(provider, model_version="t", min_history_matches=3)
    prediction = asyncio.run(engine.predict("fd-4"))
    p = prediction.probabilities
    assert prediction.home_team == "Arsenal" and prediction.freshness.is_simulated is False
    assert abs(p.home_win + p.draw + p.away_win - 1) < 1e-9
    assert not any("SIMULATED" in f for f in prediction.key_factors)


def test_chat_survives_sports_outage(settings: Settings, forex_provider: Any) -> None:
    api = FakeApi()
    api.fail_with = 503
    container = build_container(settings, sports_provider=_provider(api), forex_provider=forex_provider)
    with TestClient(create_app(settings, container)) as client:
        body = client.post("/api/v1/chat", json={"message": "Habari Sokokali"}).json()
        assert body["intent"] == "greeting"
        assert client.get("/ready").status_code == 503
        assert client.get("/api/v1/fixtures").status_code == 503


# --- HTTP helper ------------------------------------------------------------------


def test_get_json_retries_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "0"}) if len(calls) < 3 else httpx.Response(200, json={"ok": 1})

    async def run() -> Any:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await get_json(client, "https://x.test/a", max_attempts=3, base_delay=0)

    assert asyncio.run(run()) == {"ok": 1}
    assert len(calls) == 3


def test_get_json_gives_up(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("slow", request=request)

    async def run() -> Any:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await get_json(client, "https://x.test/a", max_attempts=2, base_delay=0)

    with pytest.raises(UpstreamError, match="ConnectTimeout"):
        asyncio.run(run())


# --- backtesting --------------------------------------------------------------------


def _team(team_id: str) -> Team:
    return Team(team_id=team_id, name=team_id.title(), competition="Test League")


def _dominant_league(n_rounds: int = 12) -> list[MatchResult]:
    """'strong' beats everyone 3-0; the others draw 1-1 among themselves."""
    teams = [_team(t) for t in ("strong", "a", "b", "c")]
    results, day = [], 0
    start = datetime(2026, 1, 1, tzinfo=UTC)
    for _ in range(n_rounds):
        for home in teams:
            for away in teams:
                if home is away:
                    continue
                day += 1
                if home.team_id == "strong":
                    score = (3, 0)
                elif away.team_id == "strong":
                    score = (0, 3)
                else:
                    score = (1, 1)
                results.append(
                    MatchResult(
                        match_id=f"m{day}",
                        competition="Test League",
                        home_team=home,
                        away_team=away,
                        kickoff=start + timedelta(days=day),
                        home_goals=score[0],
                        away_goals=score[1],
                    )
                )
    return results


def test_backtest_beats_baseline_on_learnable_data() -> None:
    report = backtest(_dominant_league(), warmup_matches=24)
    by_model = {m.model: m for m in report.metrics}
    assert report.matches_evaluated == len(_dominant_league()) - 24
    assert by_model["blend"].log_loss < by_model["baseline"].log_loss
    assert by_model["blend"].brier_score < by_model["baseline"].brier_score
    assert report.best_model() != "baseline"


def test_backtest_metrics_are_well_formed(provider: Any) -> None:
    report = backtest(asyncio.run(provider.get_results()), warmup_matches=20)
    assert set(report.competitions) == {"Premier League (simulated)", "Kenyan Premier League (simulated)"}
    assert abs(sum(report.outcome_frequencies.values()) - 1) < 1e-3
    for m in report.metrics:
        assert m.matches == report.matches_evaluated == 2 * (56 - 20)
        assert 0 < m.log_loss < 5 and 0 <= m.brier_score <= 2 and 0 <= m.accuracy <= 1
        assert sum(b.count for b in m.calibration) == 3 * m.matches  # three outcome probabilities per match
        assert all(b.lower <= b.mean_predicted <= b.upper for b in m.calibration)


def test_backtest_never_trains_on_the_future(monkeypatch: pytest.MonkeyPatch) -> None:
    results = _dominant_league(4)
    seen: list[datetime] = []
    real_fit = backtest_module.fit_model

    def spy(train: list[MatchResult]):  # type: ignore[no-untyped-def]
        seen.append(max(r.kickoff for r in train))
        return real_fit(train)

    monkeypatch.setattr(backtest_module, "fit_model", spy)
    backtest(results, warmup_matches=10, refit_every=1)
    # With refit_every=1 there is one fit per predicted match; its newest training match must be older.
    targets = sorted(results, key=lambda r: r.kickoff)[10:]
    assert len(seen) == len(targets)
    for latest_training_kickoff, target in zip(seen, targets, strict=True):
        assert latest_training_kickoff < target.kickoff


def test_fit_model_rejects_empty_history() -> None:
    from app.services.prediction_engine import InsufficientDataError

    with pytest.raises(InsufficientDataError):
        fit_model([])


def test_unknown_team_rated_as_league_average(provider: Any) -> None:
    engine = PredictionEngine(provider, model_version="t")
    fixture = asyncio.run(provider.get_fixtures())[0]
    newcomer = fixture.model_copy(update={"home_team": _team("newly-promoted")})
    prediction = asyncio.run(engine.predict_fixture(newcomer))
    assert any("rated as league average" in f for f in prediction.key_factors)


def test_evaluation_endpoint_and_cache(client: TestClient, container: Any) -> None:
    body = client.get("/api/v1/models/evaluation", params={"warmup": 20}).json()
    assert body["matches_evaluated"] == 72
    assert [m["model"] for m in body["metrics"]] == ["baseline", "poisson", "elo", "blend"]
    first = asyncio.run(container.predictions.evaluate(warmup_matches=20))
    assert asyncio.run(container.predictions.evaluate(warmup_matches=20)) is first  # cached
    assert client.get("/api/v1/models/evaluation", params={"warmup": 1}).status_code == 422


def test_evaluate_cli_renders(provider: Any) -> None:
    from app.evaluate import render

    text = render(backtest(asyncio.run(provider.get_results())), show_calibration=True, source="SIMULATED data")
    assert "Best by log loss" in text and "Calibration - blend" in text and "SIMULATED" in text
    json.dumps(text)  # plain text, safe to log
