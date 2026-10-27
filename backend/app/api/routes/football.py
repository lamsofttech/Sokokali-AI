"""Historical football analysis (Premier League since 1993/94) for analysts, the presenter and training."""

import logging
from datetime import date
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_container
from app.core.background import spawn
from app.core.container import Container
from app.core.security import require_admin
from app.history.ingest import ingest, parse_season
from app.history.service import HistoryService, HistoryUnavailableError, UnknownTeamError
from app.schemas.history import HeadToHead, HistoryCoverage, LeagueTable, TeamHistory, TeamStats

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/football", tags=["football history"])

ContainerDep = Annotated[Container, Depends(get_container)]
TeamQuery = Annotated[str, Query(min_length=2, max_length=50)]


def _history(container: Container) -> HistoryService:
    if not container.history.loaded:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "No historical data loaded: run `python -m app.history.ingest` or POST /api/v1/football/history/refresh",
        )
    return container.history


def _not_found(exc: UnknownTeamError) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown team or season: {exc}")


@router.get("/coverage", response_model=HistoryCoverage, summary="Which seasons and how many matches are loaded")
async def coverage(container: ContainerDep) -> HistoryCoverage:
    return container.history.coverage()


@router.get("/teams", summary="All clubs in the historical data")
async def teams(container: ContainerDep) -> list[str]:
    return _history(container).teams


@router.get("/head-to-head", response_model=HeadToHead, summary="All-time head-to-head between two clubs")
async def head_to_head(
    container: ContainerDep,
    team_a: TeamQuery,
    team_b: TeamQuery,
    recent: Annotated[int, Query(ge=1, le=50)] = 10,
) -> HeadToHead:
    try:
        return _history(container).head_to_head(team_a, team_b, recent)
    except UnknownTeamError as exc:
        raise _not_found(exc) from None


@router.get("/teams/{team}/stats", response_model=TeamStats, summary="A club's stats over recent seasons")
async def team_stats(
    container: ContainerDep,
    team: str,
    seasons: Annotated[int, Query(ge=1, le=40)] = 3,
    venue: Literal["all", "home", "away"] = "all",
    before: date | None = None,
) -> TeamStats:
    try:
        return _history(container).team_stats(team, seasons, venue, before)
    except UnknownTeamError as exc:
        raise _not_found(exc) from None


@router.get("/teams/{team}/history", response_model=TeamHistory, summary="A club's finish in every season")
async def team_history(container: ContainerDep, team: str) -> TeamHistory:
    try:
        return _history(container).team_history(team)
    except UnknownTeamError as exc:
        raise _not_found(exc) from None


@router.get("/table", response_model=LeagueTable, summary="League table for a season, optionally as of a date")
async def table(
    container: ContainerDep,
    season: Annotated[str | None, Query(max_length=9, description="e.g. 2024/25; default latest")] = None,
    as_of: date | None = None,
) -> LeagueTable:
    try:
        return _history(container).league_table(parse_season(season) if season else None, as_of)
    except (UnknownTeamError, ValueError) as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown season: {exc}") from None
    except HistoryUnavailableError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from None


@router.post(
    "/history/refresh",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_admin)],
    summary="Download/update the historical data in the background, then reload it (admin)",
)
async def refresh_history(
    container: ContainerDep,
    first_season: Annotated[int, Query(ge=1993, le=2100)] = 1993,
) -> dict[str, str]:
    if container.storage is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "No database configured (SOKOKALI_DATABASE_URL)")

    async def run() -> None:
        stored = await ingest(container.storage.engine, first_season=first_season, cache_dir=Path("data/history"))  # type: ignore[union-attr]
        loaded = await container.history.load()
        logger.info("history_refreshed", extra={"seasons": len(stored), "matches": loaded})

    spawn(run(), "history_refresh")
    return {"status": "started", "detail": "Check GET /api/v1/football/coverage in a minute"}
