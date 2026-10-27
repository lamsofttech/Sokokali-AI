"""Database tables (SQLAlchemy 2.0). Created on startup; see docs/deployment.md for migrations."""

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class PredictionRecord(Base):
    """Every distinct prediction Sokokali produced: what the model said, with which version, on which data."""

    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[str] = mapped_column(String(100), index=True)
    competition: Mapped[str] = mapped_column(String(200))
    home_team: Mapped[str] = mapped_column(String(100))
    away_team: Mapped[str] = mapped_column(String(100))
    kickoff: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    predicted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    data_as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    data_source: Mapped[str] = mapped_column(String(50))
    is_simulated: Mapped[bool] = mapped_column(Boolean)
    home_win: Mapped[float] = mapped_column(Float)
    draw: Mapped[float] = mapped_column(Float)
    away_win: Mapped[float] = mapped_column(Float)
    expected_goals_home: Mapped[float] = mapped_column(Float)
    expected_goals_away: Mapped[float] = mapped_column(Float)
    model_version: Mapped[str] = mapped_column(String(50), index=True)


class BroadcastLogRecord(Base):
    """Everything Sokokali said on air, for review and audits (human oversight)."""

    __tablename__ = "broadcast_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source: Mapped[str] = mapped_column(String(40))  # viewer, trivia, poll, milestone, ...
    viewer_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    reply: Mapped[str] = mapped_column(Text)
    engine: Mapped[str | None] = mapped_column(String(10), nullable=True)


class GamificationSnapshot(Base):
    """Single-row snapshot of points, milestones and cosmetics so they survive restarts."""

    __tablename__ = "gamification_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    state: Mapped[dict[str, Any]] = mapped_column(JSON)


class HistoricalMatch(Base):
    """One finished match from the historical football database (source: football-data.co.uk)."""

    __tablename__ = "historical_matches"
    __table_args__ = (UniqueConstraint("league", "match_date", "home_team", "away_team", name="uq_historical_match"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    league: Mapped[str] = mapped_column(String(10), index=True)  # football-data code, e.g. E0 = Premier League
    season: Mapped[str] = mapped_column(String(4), index=True)  # e.g. "2425" = 2024/25
    match_date: Mapped[date] = mapped_column(Date, index=True)
    kickoff_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    home_team: Mapped[str] = mapped_column(String(50), index=True)
    away_team: Mapped[str] = mapped_column(String(50), index=True)
    home_goals: Mapped[int] = mapped_column(Integer)
    away_goals: Mapped[int] = mapped_column(Integer)
    result: Mapped[str] = mapped_column(String(1))  # H, D, A
    ht_home_goals: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ht_away_goals: Mapped[int | None] = mapped_column(Integer, nullable=True)
    referee: Mapped[str | None] = mapped_column(String(50), nullable=True)
    home_shots: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_shots: Mapped[int | None] = mapped_column(Integer, nullable=True)
    home_shots_on_target: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_shots_on_target: Mapped[int | None] = mapped_column(Integer, nullable=True)
    home_corners: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_corners: Mapped[int | None] = mapped_column(Integer, nullable=True)
    home_fouls: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_fouls: Mapped[int | None] = mapped_column(Integer, nullable=True)
    home_yellows: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_yellows: Mapped[int | None] = mapped_column(Integer, nullable=True)
    home_reds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_reds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Market average pre-match odds (decimal); None where the source has none.
    odds_home: Mapped[float | None] = mapped_column(Float, nullable=True)
    odds_draw: Mapped[float | None] = mapped_column(Float, nullable=True)
    odds_away: Mapped[float | None] = mapped_column(Float, nullable=True)
    odds_over_25: Mapped[float | None] = mapped_column(Float, nullable=True)
    odds_under_25: Mapped[float | None] = mapped_column(Float, nullable=True)
