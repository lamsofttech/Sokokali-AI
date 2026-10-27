"""Database tables (SQLAlchemy 2.0). Created on startup; see docs/deployment.md for migrations."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text
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
