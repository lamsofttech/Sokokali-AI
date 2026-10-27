"""Historical football analysis results (from the historical_matches table)."""

from datetime import date

from pydantic import BaseModel, Field


class PastMatch(BaseModel):
    date: date
    season: str
    home_team: str
    away_team: str
    home_goals: int
    away_goals: int
    ht_score: str | None = None


class HistoryCoverage(BaseModel):
    leagues: list[str]
    seasons: list[str]
    matches: int
    first_date: date | None
    last_date: date | None
    teams: int
    source: str = "football-data.co.uk"


class HeadToHead(BaseModel):
    team_a: str
    team_b: str
    matches: int
    team_a_wins: int
    draws: int
    team_b_wins: int
    team_a_goals: int
    team_b_goals: int
    avg_total_goals: float
    over_2_5_pct: float
    btts_pct: float = Field(description="Both teams scored, % of matches")
    team_a_home_record: str = Field(description="W-D-L for team A at home against team B")
    team_a_away_record: str = Field(description="W-D-L for team A away at team B")
    recent: list[PastMatch] = Field(description="Most recent meetings, newest first")
    biggest_team_a_win: PastMatch | None = None
    biggest_team_b_win: PastMatch | None = None


class TeamStats(BaseModel):
    team: str
    venue: str = Field(description="all, home or away")
    seasons: list[str]
    played: int
    wins: int
    draws: int
    losses: int
    win_pct: float
    points_per_game: float
    goals_for: int
    goals_against: int
    avg_goals_for: float
    avg_goals_against: float
    clean_sheet_pct: float
    failed_to_score_pct: float
    btts_pct: float
    over_2_5_pct: float
    avg_shots_for: float | None = None
    avg_shots_on_target_for: float | None = None
    avg_shots_against: float | None = None
    avg_corners_for: float | None = None
    avg_yellow_cards: float | None = None
    form_last_10: str = Field(description="Most recent first, e.g. WWDLW...")
    current_streak: str
    last_matches: list[PastMatch]


class TableRow(BaseModel):
    position: int
    team: str
    played: int
    wins: int
    draws: int
    losses: int
    goals_for: int
    goals_against: int
    goal_difference: int
    points: int


class LeagueTable(BaseModel):
    season: str
    season_label: str
    as_of: date | None
    rows: list[TableRow]


class SeasonRecord(BaseModel):
    season: str
    season_label: str
    position: int
    played: int
    points: int
    goals_for: int
    goals_against: int


class TeamHistory(BaseModel):
    team: str
    seasons_in_league: int
    best_finish: SeasonRecord | None
    seasons: list[SeasonRecord] = Field(description="Newest first")
