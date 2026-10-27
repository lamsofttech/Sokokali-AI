"""Load historical results into the database from football-data.co.uk.

Run from the ``backend`` directory (needs SOKOKALI_DATABASE_URL, e.g. the Docker PostgreSQL):

    python -m app.history.ingest                      # all Premier League seasons since 1993/94
    python -m app.history.ingest --from 2015 --refresh

Downloaded files are cached in ``data/history`` so re-runs are fast; the current
season is always re-downloaded because it changes every matchweek.
Data: Football-Data.co.uk (https://www.football-data.co.uk), free for personal and
non-commercial use; check their terms before commercial use.
"""

import argparse
import asyncio
import csv
import io
import logging
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.database.models import Base, HistoricalMatch

logger = logging.getLogger(__name__)

BASE_URL = "https://football-data.co.uk/mmz4281"
LEAGUES = {"E0": "Premier League"}
FIRST_SEASON = 1993


def season_code(start_year: int) -> str:
    """1993 -> "9394", 2024 -> "2425"."""
    return f"{start_year % 100:02d}{(start_year + 1) % 100:02d}"


def season_label(code: str) -> str:
    """ "2425" -> "2024/25"."""
    first = int(code[:2])
    century = 1900 if first >= 90 else 2000
    return f"{century + first}/{code[2:]}"


def parse_season(text: str) -> str:
    """Season code from user input: "2024/25", "2024-25", "2024", "24/25" or "2425" -> "2425"."""
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) == 4 and not text.strip().isdigit() and ("/" in text or "-" in text):
        return digits  # "24/25"
    if len(digits) >= 4:
        year = int(digits[:4])
        if 1900 < year < 2100:
            return season_code(year)
        return digits[:4]
    raise ValueError(f"Unrecognised season {text!r}")


def current_season_start(today: date | None = None) -> int:
    today = today or datetime.now(UTC).date()
    return today.year if today.month >= 7 else today.year - 1


def _int(row: dict[str, str], *keys: str) -> int | None:
    for key in keys:
        value = (row.get(key) or "").strip()
        if value:
            try:
                return int(float(value))
            except ValueError:
                return None
    return None


def _float(row: dict[str, str], *keys: str) -> float | None:
    for key in keys:
        value = (row.get(key) or "").strip()
        if value:
            try:
                return float(value)
            except ValueError:
                continue
    return None


def _date(value: str) -> date | None:
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


def parse_season_csv(text: str, league: str, code: str) -> list[dict[str, Any]]:
    """Rows for HistoricalMatch. Handles the column differences between old and new seasons."""
    rows: list[dict[str, Any]] = []
    for raw in csv.DictReader(io.StringIO(text.lstrip("﻿"))):
        row = {(k or "").strip(): (v or "") for k, v in raw.items()}
        match_date = _date(row.get("Date", ""))
        home, away = row.get("HomeTeam", "").strip(), row.get("AwayTeam", "").strip()
        home_goals, away_goals = _int(row, "FTHG", "HG"), _int(row, "FTAG", "AG")
        if not (match_date and home and away) or home_goals is None or away_goals is None:
            continue  # blank trailing lines, abandoned matches
        result = (row.get("FTR") or row.get("Res") or "").strip()
        if result not in ("H", "D", "A"):
            result = "H" if home_goals > away_goals else "A" if away_goals > home_goals else "D"
        rows.append(
            {
                "league": league,
                "season": code,
                "match_date": match_date,
                "kickoff_time": (row.get("Time") or "").strip()[:5] or None,
                "home_team": home,
                "away_team": away,
                "home_goals": home_goals,
                "away_goals": away_goals,
                "result": result,
                "ht_home_goals": _int(row, "HTHG"),
                "ht_away_goals": _int(row, "HTAG"),
                "referee": (row.get("Referee") or "").strip()[:50] or None,
                "home_shots": _int(row, "HS"),
                "away_shots": _int(row, "AS"),
                "home_shots_on_target": _int(row, "HST"),
                "away_shots_on_target": _int(row, "AST"),
                "home_corners": _int(row, "HC"),
                "away_corners": _int(row, "AC"),
                "home_fouls": _int(row, "HF"),
                "away_fouls": _int(row, "AF"),
                "home_yellows": _int(row, "HY"),
                "away_yellows": _int(row, "AY"),
                "home_reds": _int(row, "HR"),
                "away_reds": _int(row, "AR"),
                # Market averages, then older market-average columns, then a single bookmaker.
                "odds_home": _float(row, "AvgH", "BbAvH", "B365H"),
                "odds_draw": _float(row, "AvgD", "BbAvD", "B365D"),
                "odds_away": _float(row, "AvgA", "BbAvA", "B365A"),
                "odds_over_25": _float(row, "Avg>2.5", "BbAv>2.5", "B365>2.5"),
                "odds_under_25": _float(row, "Avg<2.5", "BbAv<2.5", "B365<2.5"),
            }
        )
    # The unique key is (league, date, home, away); keep the last row if the source repeats one.
    unique = {(r["match_date"], r["home_team"], r["away_team"]): r for r in rows}
    return list(unique.values())


async def _download(client: httpx.AsyncClient, url: str, attempts: int = 3) -> str | None:
    for attempt in range(1, attempts + 1):
        try:
            response = await client.get(url)
            if response.status_code == 404:
                return None  # season not published yet
            response.raise_for_status()
            content = response.content
            for encoding in ("utf-8-sig", "latin-1"):
                try:
                    return content.decode(encoding)
                except UnicodeDecodeError:
                    continue
        except httpx.HTTPError as exc:
            if attempt == attempts:
                raise
            logger.warning("history_download_retry", extra={"url": url, "error": str(exc)})
            await asyncio.sleep(attempt)
    return None


async def fetch_season(
    client: httpx.AsyncClient, league: str, code: str, cache_dir: Path, refresh: bool
) -> str | None:
    cache = cache_dir / f"{league}_{code}.csv"
    if cache.exists() and not refresh:
        return cache.read_text(encoding="utf-8")
    text = await _download(client, f"{BASE_URL}/{code}/{league}.csv")
    if text is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache.write_text(text, encoding="utf-8")
    return text


async def ingest(
    engine: AsyncEngine,
    league: str = "E0",
    first_season: int = FIRST_SEASON,
    last_season: int | None = None,
    cache_dir: Path = Path("data/history"),
    refresh: bool = False,
    client: httpx.AsyncClient | None = None,
) -> dict[str, int]:
    """Download and store every season in range; returns matches stored per season code."""
    last_season = last_season if last_season is not None else current_season_start()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=30, follow_redirects=True, headers={"User-Agent": "Sokokali/1.0"})
    stored: dict[str, int] = {}
    try:
        for start in range(first_season, last_season + 1):
            code = season_code(start)
            is_current = start == current_season_start()
            text = await fetch_season(client, league, code, cache_dir, refresh or is_current)
            if text is None:
                continue
            rows = parse_season_csv(text, league, code)
            async with sessions() as session, session.begin():
                await session.execute(
                    delete(HistoricalMatch).where(HistoricalMatch.league == league, HistoricalMatch.season == code)
                )
                session.add_all(HistoricalMatch(**r) for r in rows)
            stored[code] = len(rows)
            logger.info("history_season_loaded", extra={"season": season_label(code), "matches": len(rows)})
    finally:
        if owns_client:
            await client.aclose()
    return stored


async def _main(args: argparse.Namespace) -> None:
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.core.config import get_settings

    settings = get_settings()
    if settings.database_url is None:
        raise SystemExit(
            "Set SOKOKALI_DATABASE_URL first, e.g. the Docker database: "
            "postgresql+asyncpg://sokokali:sokokali-local-only@localhost:5432/sokokali "
            "(needs the postgres port published) or sqlite+aiosqlite:///./sokokali.db"
        )
    engine = create_async_engine(settings.database_url.get_secret_value())
    try:
        stored = await ingest(
            engine, args.league, args.first, args.last, Path(args.cache_dir), refresh=args.refresh
        )
    finally:
        await engine.dispose()
    total = sum(stored.values())
    print(f"Loaded {total} {LEAGUES.get(args.league, args.league)} matches from {len(stored)} seasons")
    for code, n in stored.items():
        print(f"  {season_label(code)}: {n}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Load historical football results into Sokokali's database")
    parser.add_argument("--league", default="E0", help="football-data.co.uk league code (E0 = Premier League)")
    parser.add_argument("--from", dest="first", type=int, default=FIRST_SEASON, help="first season start year")
    parser.add_argument("--to", dest="last", type=int, default=None, help="last season start year (default: current)")
    parser.add_argument("--cache-dir", default="data/history", help="where downloaded CSV files are kept")
    parser.add_argument("--refresh", action="store_true", help="re-download every season")
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(_main(parser.parse_args()))


if __name__ == "__main__":
    main()
