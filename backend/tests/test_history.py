"""Historical football database: parsing, ingest, analysis, API and Claude tools (offline, SQLite)."""

import asyncio
import json
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import Settings
from app.core.container import build_container
from app.database.storage import Storage
from app.history.ingest import ingest, parse_season, parse_season_csv, season_label
from app.history.service import HistoryService, HistoryUnavailableError, UnknownTeamError
from app.history.teams import canonical_team, find_teams_in_text
from app.main import create_app
from app.services.llm_tools import ToolExecutor
from tests.test_live import IdleSource

OLD = """Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,,,
E0,14/08/93,Arsenal,Coventry,0,3,A,,,
E0,21/08/93,Chelsea,Arsenal,1,1,D,,,
,,,,,,,,,
"""
NEW = (
    "﻿Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR,Referee,HS,AS,HST,AST,HF,AF,HC,AC,HY,AY,HR,AR,"
    "AvgH,AvgD,AvgA,Avg>2.5,Avg<2.5\n"
    "E0,16/08/2024,20:00,Arsenal,Chelsea,3,1,H,1,0,H,M Oliver,15,8,7,3,10,12,6,2,1,3,0,0,1.9,3.6,4.1,1.7,2.1\n"
    "E0,24/08/2024,15:00,Chelsea,Tottenham,2,2,D,1,1,D,A Taylor,12,11,5,4,9,9,5,5,2,2,0,1,2.1,3.5,3.4,1.6,2.3\n"
    "E0,31/08/2024,17:30,Tottenham,Arsenal,0,1,A,0,0,D,S Hooper,9,14,2,6,11,8,3,7,3,1,0,0,2.9,3.6,2.4,1.7,2.2\n"
    "E0,14/09/2024,12:30,Chelsea,Arsenal,0,0,D,0,0,D,M Oliver,10,10,3,3,12,12,4,4,2,2,0,0,2.6,3.4,2.7,1.8,2.0\n"
)


def _transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if "/9394/" in request.url.path:
            return httpx.Response(200, content=OLD.encode())
        if "/2425/" in request.url.path:
            return httpx.Response(200, content=NEW.encode("utf-8"))
        return httpx.Response(404)

    return httpx.MockTransport(handler)


async def _loaded_service(tmp_path: Path) -> HistoryService:
    storage = Storage(f"sqlite+aiosqlite:///{(tmp_path / 'h.db').as_posix()}")
    async with httpx.AsyncClient(transport=_transport()) as client:
        stored = await ingest(storage.engine, first_season=1993, last_season=1993, cache_dir=tmp_path, client=client)
        stored.update(
            await ingest(storage.engine, first_season=2024, last_season=2024, cache_dir=tmp_path, client=client)
        )
    assert stored == {"9394": 2, "2425": 4}
    service = HistoryService(storage)
    assert await service.load() == 6
    return service


@pytest.fixture
def history(tmp_path: Path) -> HistoryService:
    return asyncio.run(_loaded_service(tmp_path))


def test_parse_old_and_new_formats() -> None:
    old = parse_season_csv(OLD, "E0", "9394")
    new = parse_season_csv(NEW, "E0", "2425")
    assert len(old) == 2 and old[0]["match_date"].isoformat() == "1993-08-14" and old[0]["home_shots"] is None
    first = new[0]
    assert first["home_team"] == "Arsenal" and first["referee"] == "M Oliver" and first["home_shots_on_target"] == 7
    assert first["odds_home"] == 1.9 and first["odds_over_25"] == 1.7 and first["kickoff_time"] == "20:00"


def test_seasons() -> None:
    assert season_label("9394") == "1993/94" and season_label("2425") == "2024/25"
    assert parse_season("2024/25") == parse_season("2024") == parse_season("24/25") == "2425"


def test_team_names() -> None:
    known = {"Man United", "Tottenham", "Nott'm Forest", "Arsenal"}
    assert canonical_team("Manchester United") == "Man United"
    assert canonical_team("spurs") == "Tottenham"
    assert canonical_team("Nottingham Forest") == "Nott'm Forest"
    assert canonical_team("Real Madrid", known) is None
    assert find_teams_in_text("Spurs vs Man Utd and the Gunners", known) == ["Tottenham", "Man United", "Arsenal"]


def test_head_to_head(history: HistoryService) -> None:
    h = history.head_to_head("arsenal", "Chelsea FC")
    assert (h.matches, h.team_a_wins, h.draws, h.team_b_wins) == (3, 1, 2, 0)
    assert (h.team_a_goals, h.team_b_goals) == (4, 2)
    assert h.team_a_home_record == "1-0-0" and h.team_a_away_record == "0-2-0"
    assert h.recent[0].date.isoformat() == "2024-09-14"  # newest first
    assert h.biggest_team_a_win is not None and h.biggest_team_a_win.home_goals == 3
    assert h.over_2_5_pct == pytest.approx(33.3) and h.btts_pct == pytest.approx(66.7)


def test_team_stats_and_streak(history: HistoryService) -> None:
    s = history.team_stats("Arsenal", seasons=1)
    assert s.seasons == ["2425"] and (s.played, s.wins, s.draws, s.losses) == (3, 2, 1, 0)
    assert s.form_last_10 == "DWW" and s.current_streak == "unbeaten in 3"
    assert s.avg_shots_for == pytest.approx((15 + 14 + 10) / 3, abs=0.01)
    away = history.team_stats("Arsenal", seasons=1, venue="away")
    assert away.played == 2 and away.clean_sheet_pct == 100.0


def test_league_table_and_history(history: HistoryService) -> None:
    table = history.league_table("2425")
    assert [r.team for r in table.rows] == ["Arsenal", "Chelsea", "Tottenham"]
    assert table.rows[0].points == 7 and table.rows[0].goal_difference == 3
    early = history.league_table("2425", as_of=date(2024, 8, 20))  # only the first matchweek counts
    assert [(r.team, r.played, r.points) for r in early.rows] == [("Arsenal", 1, 3), ("Chelsea", 1, 0)]
    past = history.team_history("Arsenal")
    assert [r.season for r in past.seasons] == ["2425", "9394"]
    assert past.best_finish is not None and past.best_finish.position == 1


def test_errors() -> None:
    empty = HistoryService(None)
    with pytest.raises(HistoryUnavailableError):
        empty.head_to_head("Arsenal", "Chelsea")
    assert asyncio.run(empty.load()) == 0


def test_unknown_team(history: HistoryService) -> None:
    with pytest.raises(UnknownTeamError):
        history.team_stats("Real Madrid")


def test_claude_history_tools(history: HistoryService, container: Any) -> None:
    executor = ToolExecutor(container.sports, container.predictions, container.forex)
    executor.history = history

    async def run() -> list[Any]:
        return [
            await executor.execute("get_head_to_head_history", {"team_a": "Arsenal", "team_b": "Chelsea"}),
            await executor.execute("get_team_history_stats", {"team": "spurs", "venue": "home", "seasons": 1}),
            await executor.execute("get_league_table_history", {"season": "2024/25"}),
            await executor.execute("get_team_history_stats", {"team": "Real Madrid", "venue": "all", "seasons": 3}),
        ]

    h2h, stats, table, unknown = asyncio.run(run())
    assert json.loads(h2h.content)["team_a_wins"] == 1 and json.loads(h2h.content)["data_is_simulated"] is False
    assert json.loads(stats.content)["team"] == "Tottenham" and json.loads(stats.content)["venue"] == "home"
    assert json.loads(table.content)["rows"][0]["team"] == "Arsenal"
    assert unknown.is_error and "Unknown team" in unknown.content


def test_football_api(settings: Settings, provider: Any, forex_provider: Any, tmp_path: Path) -> None:
    db = tmp_path / "api.db"
    url = f"sqlite+aiosqlite:///{db.as_posix()}"
    asyncio.run(_ingest_into(url, tmp_path))
    s = settings.model_copy(update={"database_url": SecretStr(url)})
    container = build_container(s, sports_provider=provider, forex_provider=forex_provider, live_source=IdleSource())
    with TestClient(create_app(s, container)) as client:
        assert client.get("/api/v1/football/coverage").json()["matches"] == 6
        h2h = client.get("/api/v1/football/head-to-head", params={"team_a": "Gunners", "team_b": "Chelsea"}).json()
        assert h2h["team_a"] == "Arsenal" and h2h["matches"] == 3
        assert client.get("/api/v1/football/table", params={"season": "2024/25"}).json()["rows"][0]["points"] == 7
        assert client.get("/api/v1/football/teams/arsenal/stats", params={"seasons": 1}).json()["wins"] == 2
        assert client.get("/api/v1/football/teams/arsenal/history").json()["seasons_in_league"] == 2
        assert client.get("/api/v1/football/teams/barcelona/stats").status_code == 404
        assert client.get("/api/v1/football/table", params={"season": "1850/51"}).status_code == 404


async def _ingest_into(url: str, tmp_path: Path) -> None:
    storage = Storage(url)
    async with httpx.AsyncClient(transport=_transport()) as client:
        for year in (1993, 2024):
            await ingest(storage.engine, first_season=year, last_season=year, cache_dir=tmp_path, client=client)
    await storage.aclose()


def test_football_api_without_data(client: TestClient) -> None:
    assert client.get("/api/v1/football/coverage").json()["matches"] == 0
    assert client.get("/api/v1/football/head-to-head", params={"team_a": "Arsenal", "team_b": "Chelsea"}).status_code == 503
