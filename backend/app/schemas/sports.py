"""Sports data contracts shared by providers, services and the API."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.schemas.common import DataFreshness


class MatchStatus(StrEnum):
    SCHEDULED = "scheduled"
    LIVE = "live"
    FINISHED = "finished"


class Team(BaseModel):
    team_id: str
    name: str
    competition: str
    aliases: list[str] = Field(default_factory=list, description="Lower-case names viewers may use")


class Fixture(BaseModel):
    match_id: str
    competition: str
    home_team: Team
    away_team: Team
    kickoff: datetime
    status: MatchStatus = MatchStatus.SCHEDULED


class MatchResult(Fixture):
    home_goals: int = Field(ge=0)
    away_goals: int = Field(ge=0)
    status: MatchStatus = MatchStatus.FINISHED


class FixtureList(BaseModel):
    fixtures: list[Fixture]
    freshness: DataFreshness


class Probabilities(BaseModel):
    home_win: float = Field(ge=0, le=1)
    draw: float = Field(ge=0, le=1)
    away_win: float = Field(ge=0, le=1)


class ExpectedGoals(BaseModel):
    home: float = Field(ge=0)
    away: float = Field(ge=0)


class Prediction(BaseModel):
    match_id: str
    competition: str
    home_team: str
    away_team: str
    kickoff: datetime
    predicted_at: datetime
    freshness: DataFreshness
    probabilities: Probabilities
    expected_goals: ExpectedGoals
    model_version: str
    key_factors: list[str]
    disclaimer: str = (
        "Probabilities are model estimates, not guaranteed outcomes. "
        "Do not treat them as betting advice."
    )
