"""Interface every sports data provider must implement.

Real providers (Phase 3) implement the same contract, so services never need
to know whether data is simulated or live.
"""

from abc import ABC, abstractmethod
from datetime import UTC, datetime

from app.schemas.sports import DataFreshness, Fixture, MatchResult, Team


class SportsDataError(Exception):
    """Raised when a provider cannot return data (outage, timeout, bad payload)."""


class SportsDataProvider(ABC):
    name: str
    is_simulated: bool

    @abstractmethod
    async def list_teams(self, competition: str | None = None) -> list[Team]: ...

    @abstractmethod
    async def get_fixtures(self, competition: str | None = None, limit: int = 20) -> list[Fixture]:
        """Upcoming fixtures ordered by kickoff."""

    @abstractmethod
    async def get_fixture(self, match_id: str) -> Fixture | None: ...

    @abstractmethod
    async def get_results(self, competition: str | None = None, team_id: str | None = None) -> list[MatchResult]:
        """Finished matches ordered oldest first."""

    @abstractmethod
    def data_as_of(self) -> datetime: ...

    async def health_check(self) -> bool:
        return True

    def freshness(self) -> DataFreshness:
        as_of = self.data_as_of()
        return DataFreshness(
            source=self.name,
            is_simulated=self.is_simulated,
            data_as_of=as_of,
            age_seconds=max(0.0, (datetime.now(UTC) - as_of).total_seconds()),
        )
