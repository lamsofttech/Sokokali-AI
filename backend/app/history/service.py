"""Historical football analysis over every stored match.

The whole Premier League history (~13,000 matches) fits comfortably in memory,
so it is loaded once from the database and analysed in Python. Every number here
comes straight from recorded results: this is the factual base that the
presenter, the analysts and the fine-tuned model all rely on.
"""

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.database.models import HistoricalMatch
from app.database.storage import Storage
from app.history.ingest import season_label
from app.history.teams import canonical_team, find_teams_in_text
from app.schemas.history import (
    HeadToHead,
    HistoryCoverage,
    LeagueTable,
    PastMatch,
    SeasonRecord,
    TableRow,
    TeamHistory,
    TeamStats,
)

logger = logging.getLogger(__name__)


class HistoryUnavailableError(Exception):
    """No historical data loaded (no database, or the ingest has not been run)."""


class UnknownTeamError(Exception):
    pass


@dataclass(frozen=True)
class _M:
    league: str
    season: str
    date: date
    home: str
    away: str
    hg: int
    ag: int
    ht: str | None
    hs: int | None
    as_: int | None
    hst: int | None
    ast: int | None
    hc: int | None
    ac: int | None
    hy: int | None
    ay: int | None

    def past(self) -> PastMatch:
        return PastMatch(
            date=self.date,
            season=self.season,
            home_team=self.home,
            away_team=self.away,
            home_goals=self.hg,
            away_goals=self.ag,
            ht_score=self.ht,
        )


def _pct(part: int, whole: int) -> float:
    return round(100 * part / whole, 1) if whole else 0.0


def _avg(values: list[int]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


class HistoryService:
    def __init__(self, storage: Storage | None, league: str = "E0") -> None:
        self.storage = storage
        self.league = league
        self._matches: list[_M] = []
        self._teams: set[str] = set()

    # -- loading ------------------------------------------------------------------

    async def load(self) -> int:
        """(Re)load all stored matches. Returns how many were loaded; 0 if there is no data."""
        if self.storage is None:
            return 0
        try:
            async with self.storage.engine.connect() as conn:
                rows = (
                    await conn.execute(
                        select(HistoricalMatch).where(HistoricalMatch.league == self.league).order_by(
                            HistoricalMatch.match_date, HistoricalMatch.id
                        )
                    )
                ).all()
        except SQLAlchemyError as exc:
            logger.warning("history_load_failed", extra={"error": str(exc)})
            return 0
        self._matches = [
            _M(
                r.league, r.season, r.match_date, r.home_team, r.away_team, r.home_goals, r.away_goals,
                f"{r.ht_home_goals}-{r.ht_away_goals}" if r.ht_home_goals is not None else None,
                r.home_shots, r.away_shots, r.home_shots_on_target, r.away_shots_on_target,
                r.home_corners, r.away_corners, r.home_yellows, r.away_yellows,
            )
            for r in rows
        ]
        self._teams = {m.home for m in self._matches} | {m.away for m in self._matches}
        logger.info("history_loaded", extra={"matches": len(self._matches), "teams": len(self._teams)})
        return len(self._matches)

    @property
    def loaded(self) -> bool:
        return bool(self._matches)

    def _require(self) -> None:
        if not self._matches:
            raise HistoryUnavailableError(
                "No historical data loaded. Run: python -m app.history.ingest (needs a database)"
            )

    def team(self, name: str) -> str:
        self._require()
        team = canonical_team(name, self._teams)
        if team is None or team not in self._teams:
            raise UnknownTeamError(name)
        return team

    def teams_in_text(self, text: str) -> list[str]:
        return find_teams_in_text(text, self._teams) if self._matches else []

    @property
    def teams(self) -> list[str]:
        return sorted(self._teams)

    def coverage(self) -> HistoryCoverage:
        seasons = sorted({m.season for m in self._matches}, key=lambda s: (int(s[:2]) < 90, s))
        return HistoryCoverage(
            leagues=[self.league] if self._matches else [],
            seasons=seasons,
            matches=len(self._matches),
            first_date=self._matches[0].date if self._matches else None,
            last_date=self._matches[-1].date if self._matches else None,
            teams=len(self._teams),
        )

    def _seasons_desc(self) -> list[str]:
        seen: list[str] = []
        for m in reversed(self._matches):
            if m.season not in seen:
                seen.append(m.season)
        return seen

    # -- analysis -------------------------------------------------------------------

    def head_to_head(self, team_a: str, team_b: str, recent: int = 10) -> HeadToHead:
        a, b = self.team(team_a), self.team(team_b)
        games = [m for m in self._matches if {m.home, m.away} == {a, b}]
        a_w = b_w = d = a_goals = b_goals = over = btts = 0
        home_rec = [0, 0, 0]
        away_rec = [0, 0, 0]
        best_a: tuple[int, _M] | None = None
        best_b: tuple[int, _M] | None = None
        for m in games:
            ga, gb = (m.hg, m.ag) if m.home == a else (m.ag, m.hg)
            a_goals += ga
            b_goals += gb
            over += m.hg + m.ag > 2
            btts += m.hg > 0 and m.ag > 0
            rec = home_rec if m.home == a else away_rec
            if ga > gb:
                a_w += 1
                rec[0] += 1
                if best_a is None or ga - gb > best_a[0]:
                    best_a = (ga - gb, m)
            elif ga < gb:
                b_w += 1
                rec[2] += 1
                if best_b is None or gb - ga > best_b[0]:
                    best_b = (gb - ga, m)
            else:
                d += 1
                rec[1] += 1
        n = len(games)
        return HeadToHead(
            team_a=a,
            team_b=b,
            matches=n,
            team_a_wins=a_w,
            draws=d,
            team_b_wins=b_w,
            team_a_goals=a_goals,
            team_b_goals=b_goals,
            avg_total_goals=round((a_goals + b_goals) / n, 2) if n else 0.0,
            over_2_5_pct=_pct(over, n),
            btts_pct=_pct(btts, n),
            team_a_home_record="-".join(map(str, home_rec)),
            team_a_away_record="-".join(map(str, away_rec)),
            recent=[m.past() for m in reversed(games[-recent:])],
            biggest_team_a_win=best_a[1].past() if best_a else None,
            biggest_team_b_win=best_b[1].past() if best_b else None,
        )

    def team_stats(self, team: str, seasons: int = 3, venue: str = "all", before: date | None = None) -> TeamStats:
        """Stats over the team's most recent ``seasons`` league seasons (optionally only matches before a date)."""
        t = self.team(team)
        all_games = [m for m in self._matches if t in (m.home, m.away) and (before is None or m.date < before)]
        season_ids: list[str] = []
        for m in reversed(all_games):
            if m.season not in season_ids:
                season_ids.append(m.season)
        chosen = set(season_ids[: max(1, seasons)])
        games = [
            m
            for m in all_games
            if m.season in chosen and (venue == "all" or (venue == "home") == (m.home == t))
        ]
        w = d = lost = gf = ga = cs = fts = btts = over = 0
        shots, sot, shots_against, corners, yellows = [], [], [], [], []
        letters = []
        for m in games:
            home = m.home == t
            f, a = (m.hg, m.ag) if home else (m.ag, m.hg)
            gf += f
            ga += a
            cs += a == 0
            fts += f == 0
            btts += f > 0 and a > 0
            over += f + a > 2
            letter = "W" if f > a else "D" if f == a else "L"
            letters.append(letter)
            w += letter == "W"
            d += letter == "D"
            lost += letter == "L"
            for target, value in (
                (shots, m.hs if home else m.as_),
                (sot, m.hst if home else m.ast),
                (shots_against, m.as_ if home else m.hs),
                (corners, m.hc if home else m.ac),
                (yellows, m.hy if home else m.ay),
            ):
                if value is not None:
                    target.append(value)
        n = len(games)
        form = "".join(reversed(letters[-10:]))
        return TeamStats(
            team=t,
            venue=venue,
            seasons=sorted(chosen),
            played=n,
            wins=w,
            draws=d,
            losses=lost,
            win_pct=_pct(w, n),
            points_per_game=round((3 * w + d) / n, 2) if n else 0.0,
            goals_for=gf,
            goals_against=ga,
            avg_goals_for=round(gf / n, 2) if n else 0.0,
            avg_goals_against=round(ga / n, 2) if n else 0.0,
            clean_sheet_pct=_pct(cs, n),
            failed_to_score_pct=_pct(fts, n),
            btts_pct=_pct(btts, n),
            over_2_5_pct=_pct(over, n),
            avg_shots_for=_avg(shots),
            avg_shots_on_target_for=_avg(sot),
            avg_shots_against=_avg(shots_against),
            avg_corners_for=_avg(corners),
            avg_yellow_cards=_avg(yellows),
            form_last_10=form,
            current_streak=_streak(list(reversed(letters))),
            last_matches=[m.past() for m in reversed(games[-5:])],
        )

    def league_table(self, season: str | None = None, as_of: date | None = None) -> LeagueTable:
        self._require()
        season = season or self._seasons_desc()[0]
        games = [m for m in self._matches if m.season == season and (as_of is None or m.date <= as_of)]
        if not games and season not in {m.season for m in self._matches}:
            raise UnknownTeamError(f"season {season}")
        rows = _table(games)
        return LeagueTable(season=season, season_label=season_label(season), as_of=as_of, rows=rows)

    def team_history(self, team: str) -> TeamHistory:
        t = self.team(team)
        records: list[SeasonRecord] = []
        for season in self._seasons_desc():
            table = _table([m for m in self._matches if m.season == season])
            row = next((r for r in table if r.team == t), None)
            if row:
                records.append(
                    SeasonRecord(
                        season=season,
                        season_label=season_label(season),
                        position=row.position,
                        played=row.played,
                        points=row.points,
                        goals_for=row.goals_for,
                        goals_against=row.goals_against,
                    )
                )
        best = min(records, key=lambda r: (r.position, -r.points)) if records else None
        return TeamHistory(team=t, seasons_in_league=len(records), best_finish=best, seasons=records)


def _table(games: list[_M]) -> list[TableRow]:
    stats: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0, 0, 0])  # P W D L GF GA
    for m in games:
        for team, f, a in ((m.home, m.hg, m.ag), (m.away, m.ag, m.hg)):
            s = stats[team]
            s[0] += 1
            s[1] += f > a
            s[2] += f == a
            s[3] += f < a
            s[4] += f
            s[5] += a
    ordered = sorted(
        stats.items(), key=lambda kv: (-(3 * kv[1][1] + kv[1][2]), -(kv[1][4] - kv[1][5]), -kv[1][4], kv[0])
    )
    return [
        TableRow(
            position=i,
            team=team,
            played=s[0],
            wins=s[1],
            draws=s[2],
            losses=s[3],
            goals_for=s[4],
            goals_against=s[5],
            goal_difference=s[4] - s[5],
            points=3 * s[1] + s[2],
        )
        for i, (team, s) in enumerate(ordered, start=1)
    ]


def _streak(letters_newest_first: list[str]) -> str:
    """e.g. "won 3", "unbeaten in 7", "without a win in 4"."""
    if not letters_newest_first:
        return "no matches"
    first = letters_newest_first[0]
    run = 0
    for letter in letters_newest_first:
        if letter != first:
            break
        run += 1
    if first == "W":
        unbeaten = next((i for i, x in enumerate(letters_newest_first) if x == "L"), len(letters_newest_first))
        if run == 1 and unbeaten == 1:
            return "won their last game"
        return f"won {run}" if unbeaten == run else f"won {run}, unbeaten in {unbeaten}"
    if first == "D":
        unbeaten = next((i for i, x in enumerate(letters_newest_first) if x == "L"), len(letters_newest_first))
        return "drew their last game" if unbeaten == 1 else f"unbeaten in {unbeaten}"
    winless = next((i for i, x in enumerate(letters_newest_first) if x == "W"), len(letters_newest_first))
    if run == 1 and winless == 1:
        return "lost their last game"
    return f"lost {run}" if winless == run else f"lost {run}, without a win in {winless}"
