"""Persistence for predictions, the broadcast log and gamification state.

Writes never break the show: if the database is down, the error is logged
and Sokokali carries on in memory (readiness reports the outage).
"""

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.database.models import Base, BroadcastLogRecord, GamificationSnapshot, PredictionRecord
from app.schemas.sports import Prediction

logger = logging.getLogger(__name__)


class Storage:
    def __init__(self, url: str, engine: AsyncEngine | None = None) -> None:
        # SQLite (local/tests) allows one writer at a time: wait for the lock instead of failing.
        connect_args = {"timeout": 15} if url.startswith("sqlite") else {}
        self.engine = engine or create_async_engine(url, pool_pre_ping=True, connect_args=connect_args)
        self._sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self._last_prediction: dict[str, tuple[Any, ...]] = {}

    async def init(self) -> None:
        """Create missing tables. Raises if the database is unreachable at startup."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def healthy(self) -> bool:
        try:
            async with self.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except (SQLAlchemyError, OSError):
            return False

    async def _add(self, record: Base, what: str) -> None:
        try:
            async with self._sessions() as session, session.begin():
                session.add(record)
        except (SQLAlchemyError, OSError) as exc:
            logger.warning("storage_write_failed", extra={"what": what, "error": str(exc)})

    async def save_prediction(self, p: Prediction) -> None:
        """Store a prediction, unless it is identical to the last one stored for this match."""
        probs = p.probabilities
        key = (p.model_version, p.freshness.data_as_of, probs.home_win, probs.draw, probs.away_win)
        if self._last_prediction.get(p.match_id) == key:
            return
        self._last_prediction[p.match_id] = key
        await self._add(
            PredictionRecord(
                match_id=p.match_id,
                competition=p.competition,
                home_team=p.home_team,
                away_team=p.away_team,
                kickoff=p.kickoff,
                predicted_at=p.predicted_at,
                data_as_of=p.freshness.data_as_of,
                data_source=p.freshness.source,
                is_simulated=p.freshness.is_simulated,
                home_win=probs.home_win,
                draw=probs.draw,
                away_win=probs.away_win,
                expected_goals_home=p.expected_goals.home,
                expected_goals_away=p.expected_goals.away,
                model_version=p.model_version,
            ),
            "prediction",
        )

    async def recent_predictions(self, limit: int = 50) -> list[PredictionRecord]:
        async with self._sessions() as session:
            rows = await session.scalars(
                select(PredictionRecord).order_by(PredictionRecord.predicted_at.desc()).limit(limit)
            )
            return list(rows)

    async def log_broadcast(self, say: dict[str, Any]) -> None:
        response = say.get("response") or {}
        await self._add(
            BroadcastLogRecord(
                at=datetime.now(UTC),
                source=str(say.get("source", ""))[:40],
                viewer_name=say.get("viewer_name"),
                comment=say.get("comment"),
                reply=str(say.get("text", "")),
                engine=response.get("engine"),
            ),
            "broadcast_log",
        )

    async def recent_broadcast(self, limit: int = 50) -> list[BroadcastLogRecord]:
        async with self._sessions() as session:
            rows = await session.scalars(select(BroadcastLogRecord).order_by(BroadcastLogRecord.id.desc()).limit(limit))
            return list(rows)

    async def save_gamification(self, state: dict[str, Any]) -> None:
        try:
            async with self._sessions() as session, session.begin():
                snapshot = await session.get(GamificationSnapshot, 1)
                if snapshot is None:
                    session.add(GamificationSnapshot(id=1, updated_at=datetime.now(UTC), state=state))
                else:
                    snapshot.state = state
                    snapshot.updated_at = datetime.now(UTC)
        except (SQLAlchemyError, OSError) as exc:
            logger.warning("storage_write_failed", extra={"what": "gamification", "error": str(exc)})

    async def load_gamification(self) -> dict[str, Any] | None:
        try:
            async with self._sessions() as session:
                snapshot = await session.get(GamificationSnapshot, 1)
                return dict(snapshot.state) if snapshot else None
        except (SQLAlchemyError, OSError) as exc:
            logger.warning("storage_read_failed", extra={"what": "gamification", "error": str(exc)})
            return None

    async def aclose(self) -> None:
        await self.engine.dispose()
