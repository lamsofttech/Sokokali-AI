"""Real football data from football-data.org (API v4).

One refresh downloads every match of each configured competition for the
current season and the previous ``seasons_of_history - 1`` seasons (one
request per competition-season), then serves fixtures and results from that
in-memory snapshot until it is ``cache_ttl_seconds`` old.

If a refresh fails, the previous snapshot keeps being served (its
``data_as_of`` shows how old it is). Only when no snapshot exists at all does
the provider raise ``SportsDataError``.

Free-tier accounts are limited to a few requests per minute, so keep the
competition list short and the TTL at a few minutes.
Docs: https://docs.football-data.org/general/v4/index.html
"""

import asyncio
import logging
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.http import UpstreamError, get_json
from app.integrations.sports.base import SportsDataError, SportsDataProvider
from app.schemas.sports import Fixture, MatchResult, MatchStatus, Team

logger = logging.getLogger(__name__)

_UPCOMING = {"SCHEDULED", "TIMED"}
_LIVE = {"IN_PLAY", "PAUSED"}
_SUFFIX_RE = re.compile(r"\s+(?:a?fc|cf|sc)$")


@dataclass(frozen=True)
class _Snapshot:
    teams: dict[str, Team]
    fixtures: list[Fixture]
    results: list[MatchResult]
    fetched_at: datetime
    fetched_monotonic: float


def _aliases(team: dict[str, Any]) -> list[str]:
    names = {str(team.get(k) or "").strip().lower() for k in ("name", "shortName")}
    names |= {_SUFFIX_RE.sub("", n) for n in names}
    # Three-letter codes ("NEW", "TOT") are left out: they collide with ordinary chat words.
    return sorted(n for n in names if len(n) >= 4)


class FootballDataProvider(SportsDataProvider):
    name = "football-data.org"
    is_simulated = False

    def __init__(
        self,
        api_key: str,
        competitions: list[str],
        base_url: str = "https://api.football-data.org/v4",
        seasons_of_history: int = 2,
        cache_ttl_seconds: float = 300,
        timeout_seconds: float = 10.0,
        max_attempts: int = 3,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("football-data.org needs an API key (FOOTBALL_DATA_API_KEY)")
        if not competitions:
            raise ValueError("At least one competition code is required")
        self.competitions = [c.upper() for c in competitions]
        self.base_url = base_url.rstrip("/")
        self.seasons_of_history = seasons_of_history
        self.cache_ttl_seconds = cache_ttl_seconds
        self.max_attempts = max_attempts
        self._headers = {"X-Auth-Token": api_key}
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)
        self._snapshot: _Snapshot | None = None
        self._lock = asyncio.Lock()
        self.last_error: str | None = None

    # -- snapshot management ------------------------------------------------

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return await get_json(
            self._client,
            f"{self.base_url}{path}",
            params=params,
            headers=self._headers,
            max_attempts=self.max_attempts,
        )

    async def _fetch_competition(self, code: str) -> list[dict[str, Any]]:
        current = await self._get(f"/competitions/{code}/matches")
        matches: list[dict[str, Any]] = list(current.get("matches", []))
        season_start = (current.get("filters") or {}).get("season")
        if season_start is None and matches:
            season_start = str((matches[0].get("season") or {}).get("startDate", ""))[:4]
        if season_start and str(season_start).isdigit():
            for back in range(1, self.seasons_of_history):
                older = await self._get(f"/competitions/{code}/matches", {"season": int(season_start) - back})
                matches.extend(older.get("matches", []))
        return matches

    def _parse(self, raw_by_competition: dict[str, list[dict[str, Any]]]) -> _Snapshot:
        teams: dict[str, Team] = {}
        fixtures: list[Fixture] = []
        results: list[MatchResult] = []
        for code, raw_matches in raw_by_competition.items():
            for m in raw_matches:
                try:
                    competition = (m.get("competition") or {}).get("name") or code
                    pair = []
                    for side in ("homeTeam", "awayTeam"):
                        t = m[side]
                        if t.get("id") is None:
                            raise KeyError("team id")  # e.g. knockout slot not decided yet
                        team_id = f"fd-{t['id']}"
                        if team_id not in teams:
                            teams[team_id] = Team(
                                team_id=team_id,
                                name=t.get("shortName") or t.get("name") or team_id,
                                competition=competition,
                                aliases=_aliases(t),
                            )
                        pair.append(teams[team_id])
                    common = {
                        "match_id": f"fd-{m['id']}",
                        "competition": competition,
                        "home_team": pair[0],
                        "away_team": pair[1],
                        "kickoff": datetime.fromisoformat(str(m["utcDate"]).replace("Z", "+00:00")),
                    }
                    status = m.get("status")
                    full_time = (m.get("score") or {}).get("fullTime") or {}
                    if status == "FINISHED" and full_time.get("home") is not None and full_time.get("away") is not None:
                        results.append(
                            MatchResult(**common, home_goals=int(full_time["home"]), away_goals=int(full_time["away"]))
                        )
                    elif status in _UPCOMING:
                        fixtures.append(Fixture(**common))
                    elif status in _LIVE:
                        fixtures.append(Fixture(**common, status=MatchStatus.LIVE))
                except (KeyError, TypeError, ValueError) as exc:
                    logger.debug("football_data_skipped_match", extra={"match": m.get("id"), "error": str(exc)})
        results.sort(key=lambda r: r.kickoff)
        fixtures.sort(key=lambda f: f.kickoff)
        return _Snapshot(teams, fixtures, results, datetime.now(UTC), time.monotonic())

    async def _snapshot_or_refresh(self) -> _Snapshot:
        snap = self._snapshot
        if snap is not None and time.monotonic() - snap.fetched_monotonic < self.cache_ttl_seconds:
            return snap
        async with self._lock:
            snap = self._snapshot  # another request may have refreshed while we waited
            if snap is not None and time.monotonic() - snap.fetched_monotonic < self.cache_ttl_seconds:
                return snap
            try:
                raw = {code: await self._fetch_competition(code) for code in self.competitions}
                self._snapshot = self._parse(raw)
                self.last_error = None
                logger.info(
                    "football_data_refreshed",
                    extra={"results": len(self._snapshot.results), "fixtures": len(self._snapshot.fixtures)},
                )
            except UpstreamError as exc:
                self.last_error = str(exc)
                logger.warning("football_data_refresh_failed", extra={"error": str(exc), "serving_stale": bool(snap)})
                if snap is None:
                    raise SportsDataError(f"football-data.org unavailable: {exc}") from None
            assert self._snapshot is not None
            return self._snapshot

    # -- SportsDataProvider ----------------------------------------------------

    async def list_teams(self, competition: str | None = None) -> list[Team]:
        snap = await self._snapshot_or_refresh()
        return [t for t in snap.teams.values() if competition is None or t.competition == competition]

    async def get_fixtures(self, competition: str | None = None, limit: int = 20) -> list[Fixture]:
        snap = await self._snapshot_or_refresh()
        return [f for f in snap.fixtures if competition is None or f.competition == competition][:limit]

    async def get_fixture(self, match_id: str) -> Fixture | None:
        snap = await self._snapshot_or_refresh()
        return next((f for f in snap.fixtures if f.match_id == match_id), None)

    async def get_results(self, competition: str | None = None, team_id: str | None = None) -> list[MatchResult]:
        snap = await self._snapshot_or_refresh()
        return [
            r
            for r in snap.results
            if (competition is None or r.competition == competition)
            and (team_id is None or team_id in (r.home_team.team_id, r.away_team.team_id))
        ]

    def data_as_of(self) -> datetime:
        return self._snapshot.fetched_at if self._snapshot else datetime.fromtimestamp(0, UTC)

    async def health_check(self) -> bool:
        try:
            await self._snapshot_or_refresh()
        except SportsDataError:
            return False
        return True

    async def aclose(self) -> None:
        await self._client.aclose()
