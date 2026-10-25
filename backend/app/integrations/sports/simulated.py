"""Deterministic simulated football data for local development.

Team names are real clubs, but every result and fixture produced here is
SYNTHETIC. All data is flagged ``is_simulated=True`` so it can never be
mistaken for real-world information.
"""

import math
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.integrations.sports.base import SportsDataProvider
from app.schemas.sports import Fixture, MatchResult, Team


@dataclass(frozen=True)
class _SimTeam:
    team_id: str
    name: str
    aliases: tuple[str, ...]
    attack: float  # hidden "true" strengths used only to generate synthetic results
    defence: float


_COMPETITIONS: dict[str, tuple[str, float, float, list[_SimTeam]]] = {
    # code: (display name, mean home goals, mean away goals, teams)
    "epl": (
        "Premier League (simulated)",
        1.55,
        1.25,
        [
            _SimTeam("arsenal", "Arsenal", ("arsenal", "gunners", "arsenali"), 1.35, 0.75),
            _SimTeam("chelsea", "Chelsea", ("chelsea", "chelsea fc", "blues"), 1.15, 0.90),
            _SimTeam("liverpool", "Liverpool", ("liverpool", "reds"), 1.40, 0.80),
            _SimTeam("man-city", "Manchester City", ("manchester city", "man city"), 1.45, 0.75),
            _SimTeam("man-utd", "Manchester United", ("manchester united", "man united", "man utd", "man u"), 1.00, 1.05),
            _SimTeam("tottenham", "Tottenham Hotspur", ("tottenham hotspur", "tottenham", "spurs"), 1.05, 1.10),
            _SimTeam("newcastle", "Newcastle United", ("newcastle united", "newcastle"), 1.05, 0.95),
            _SimTeam("aston-villa", "Aston Villa", ("aston villa", "villa"), 1.00, 1.00),
        ],
    ),
    "kpl": (
        "Kenyan Premier League (simulated)",
        1.30,
        0.95,
        [
            _SimTeam("gor-mahia", "Gor Mahia", ("gor mahia", "gor", "k'ogalo", "kogalo"), 1.35, 0.75),
            _SimTeam("afc-leopards", "AFC Leopards", ("afc leopards", "leopards", "ingwe"), 1.10, 0.95),
            _SimTeam("tusker", "Tusker FC", ("tusker fc", "tusker"), 1.20, 0.85),
            _SimTeam("kcb", "KCB FC", ("kcb fc", "kcb", "bankers"), 1.05, 0.95),
            _SimTeam("police", "Police FC", ("police fc", "police"), 1.15, 0.90),
            _SimTeam("shabana", "Shabana FC", ("shabana fc", "shabana"), 0.95, 1.05),
            _SimTeam("bandari", "Bandari FC", ("bandari fc", "bandari"), 0.95, 1.05),
            _SimTeam("kakamega-homeboyz", "Kakamega Homeboyz", ("kakamega homeboyz", "homeboyz"), 1.00, 1.00),
        ],
    ),
}

# Upcoming fixtures: (competition, home team id, away team id, days from now, kickoff hour UTC)
_UPCOMING: list[tuple[str, str, str, int, int]] = [
    ("epl", "arsenal", "chelsea", 1, 16),
    ("epl", "liverpool", "man-city", 1, 18),
    ("kpl", "gor-mahia", "afc-leopards", 2, 12),
    ("epl", "man-utd", "tottenham", 2, 15),
    ("kpl", "tusker", "kcb", 3, 13),
    ("epl", "newcastle", "aston-villa", 3, 14),
    ("kpl", "police", "shabana", 4, 12),
    ("kpl", "bandari", "kakamega-homeboyz", 5, 13),
]


def _sample_poisson(rng: random.Random, lam: float) -> int:
    """Knuth's algorithm; fine for the small means used in football."""
    threshold = math.exp(-lam)
    k, p = 0, 1.0
    while True:
        p *= rng.random()
        if p <= threshold:
            return k
        k += 1


class SimulatedSportsProvider(SportsDataProvider):
    name = "simulated"
    is_simulated = True

    def __init__(self, seed: int = 2024, now: datetime | None = None) -> None:
        self._now = (now or datetime.now(UTC)).replace(minute=0, second=0, microsecond=0)
        self._teams: dict[str, Team] = {}
        self._results: list[MatchResult] = []
        self._fixtures: list[Fixture] = []
        self._generate(random.Random(seed))

    def _generate(self, rng: random.Random) -> None:
        for code, (competition, home_mean, away_mean, sim_teams) in _COMPETITIONS.items():
            for t in sim_teams:
                self._teams[t.team_id] = Team(
                    team_id=t.team_id, name=t.name, competition=competition, aliases=list(t.aliases)
                )
            # One full double round-robin season, played over the last ~180 days.
            pairings = [(h, a) for h in sim_teams for a in sim_teams if h is not a]
            rng.shuffle(pairings)
            for index, (home, away) in enumerate(pairings):
                kickoff = self._now - timedelta(days=180) + timedelta(days=index * 175 / len(pairings))
                self._results.append(
                    MatchResult(
                        match_id=f"sim-{code}-r{index + 1:03d}",
                        competition=competition,
                        home_team=self._teams[home.team_id],
                        away_team=self._teams[away.team_id],
                        kickoff=kickoff,
                        home_goals=_sample_poisson(rng, home_mean * home.attack * away.defence),
                        away_goals=_sample_poisson(rng, away_mean * away.attack * home.defence),
                    )
                )
        self._results.sort(key=lambda r: r.kickoff)

        for index, (code, home_id, away_id, days, hour) in enumerate(_UPCOMING):
            self._fixtures.append(
                Fixture(
                    match_id=f"sim-{code}-f{index + 1:03d}",
                    competition=_COMPETITIONS[code][0],
                    home_team=self._teams[home_id],
                    away_team=self._teams[away_id],
                    kickoff=(self._now + timedelta(days=days)).replace(hour=hour),
                )
            )
        self._fixtures.sort(key=lambda f: f.kickoff)

    async def list_teams(self, competition: str | None = None) -> list[Team]:
        return [t for t in self._teams.values() if competition is None or t.competition == competition]

    async def get_fixtures(self, competition: str | None = None, limit: int = 20) -> list[Fixture]:
        matches = [f for f in self._fixtures if competition is None or f.competition == competition]
        return matches[:limit]

    async def get_fixture(self, match_id: str) -> Fixture | None:
        return next((f for f in self._fixtures if f.match_id == match_id), None)

    async def get_results(self, competition: str | None = None, team_id: str | None = None) -> list[MatchResult]:
        return [
            r
            for r in self._results
            if (competition is None or r.competition == competition)
            and (team_id is None or team_id in (r.home_team.team_id, r.away_team.team_id))
        ]

    def data_as_of(self) -> datetime:
        return self._now
