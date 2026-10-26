"""Sports lookups used by the chat service (the "tools" Sokokali can call).

Phase 2 exposes these same methods to the LLM as structured tools.
"""

import re
from datetime import datetime

from app.integrations.sports.base import SportsDataProvider
from app.schemas.sports import Fixture, MatchResult, Team


class SportsService:
    def __init__(self, provider: SportsDataProvider) -> None:
        self.provider = provider
        self._alias_pattern: re.Pattern[str] | None = None
        self._alias_to_team: dict[str, Team] = {}
        self._aliases_as_of: datetime | None = None

    async def _ensure_aliases(self) -> None:
        teams = await self.provider.list_teams()  # may refresh the provider's data
        if self._aliases_as_of == self.provider.data_as_of():
            return
        self._alias_to_team = {}
        for team in teams:
            for alias in {team.name.lower(), *team.aliases}:
                self._alias_to_team[alias] = team
        # Longest aliases first so "man city" wins over a shorter overlapping alias.
        aliases = sorted(self._alias_to_team, key=len, reverse=True)
        self._alias_pattern = (
            re.compile(r"(?<!\w)(" + "|".join(re.escape(a) for a in aliases) + r")(?!\w)") if aliases else None
        )
        self._aliases_as_of = self.provider.data_as_of()

    async def find_teams(self, text: str) -> list[Team]:
        """Teams mentioned in ``text``, in order of first appearance, without duplicates."""
        await self._ensure_aliases()
        if self._alias_pattern is None:
            return []
        found: list[Team] = []
        for match in self._alias_pattern.finditer(text.lower()):
            team = self._alias_to_team[match.group(1)]
            if all(t.team_id != team.team_id for t in found):
                found.append(team)
        return found

    async def upcoming_fixtures(self, limit: int = 5, team: Team | None = None) -> list[Fixture]:
        fixtures = await self.provider.get_fixtures(limit=100)
        if team is not None:
            fixtures = [f for f in fixtures if team.team_id in (f.home_team.team_id, f.away_team.team_id)]
        return fixtures[:limit]

    async def fixture_between(self, team_a: Team, team_b: Team) -> Fixture | None:
        """Next scheduled meeting of the two teams, regardless of who is at home."""
        ids = {team_a.team_id, team_b.team_id}
        for fixture in await self.provider.get_fixtures(limit=100):
            if {fixture.home_team.team_id, fixture.away_team.team_id} == ids:
                return fixture
        return None

    async def last_meeting(self, team_a: Team, team_b: Team) -> MatchResult | None:
        ids = {team_a.team_id, team_b.team_id}
        meetings = [
            r
            for r in await self.provider.get_results(team_id=team_a.team_id)
            if {r.home_team.team_id, r.away_team.team_id} == ids
        ]
        return meetings[-1] if meetings else None

    async def recent_results(self, team: Team, limit: int = 5) -> list[MatchResult]:
        results = await self.provider.get_results(team_id=team.team_id)
        return list(reversed(results))[:limit]
