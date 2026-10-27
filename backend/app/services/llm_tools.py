"""Tools Claude can call, and the executor that answers them from verified data.

Every tool result is built from the sports and forex services, so any number
Sokokali says on air can be traced back to a provider. The tool list is
fixed for the lifetime of the process (it is part of the cached prompt prefix).
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from app.integrations.forex.base import ForexDataError
from app.integrations.sports.base import SportsDataError
from app.history.ingest import parse_season
from app.history.service import HistoryService, HistoryUnavailableError, UnknownTeamError
from app.schemas.forex import CurrencyPair, ForexSignal
from app.schemas.sports import Prediction, Team
from app.services.forex_engine import ForexSignalEngine, InsufficientForexDataError, PairNotFoundError
from app.services.prediction_engine import InsufficientDataError, PredictionEngine, team_form
from app.services.sports_engine import SportsService

logger = logging.getLogger(__name__)


def _tool(name: str, description: str, properties: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        },
    }


_TEAM = {"type": "string", "description": "Team name as the viewer wrote it, e.g. 'Arsenal', 'Gor Mahia', 'Ingwe'"}

SPORTS_TOOLS = [
    _tool(
        "get_upcoming_fixtures",
        "List upcoming football fixtures with kickoff times (UTC). Use when a viewer asks what matches are "
        "coming up, today, this weekend, or when a team plays next.",
        {"team": {"type": "string", "description": "Team to filter by, or an empty string for all fixtures"}},
    ),
    _tool(
        "get_match_prediction",
        "Get the model's home-win/draw/away-win probabilities, expected goals and key factors for the next "
        "scheduled match between two teams. Use for 'who will win' questions. Returns an error if the two teams "
        "have no scheduled match.",
        {"team_a": _TEAM, "team_b": _TEAM},
    ),
    _tool(
        "get_team_form",
        "Get a team's recent form (latest first), its last few results and its next fixture.",
        {"team": _TEAM},
    ),
    _tool(
        "get_head_to_head",
        "Get the most recent finished match between two teams, with the score and date.",
        {"team_a": _TEAM, "team_b": _TEAM},
    ),
]

HISTORY_TOOLS = [
    _tool(
        "get_head_to_head_history",
        "All-time Premier League head-to-head between two clubs since 1993/94: wins, draws, goals, over 2.5 and "
        "both-teams-to-score rates, home/away records, biggest wins and the most recent meetings. Use for questions "
        "about the history or rivalry between two teams.",
        {"team_a": _TEAM, "team_b": _TEAM},
    ),
    _tool(
        "get_team_history_stats",
        "A club's Premier League statistics over its most recent seasons: record, points per game, goals for "
        "and against, clean sheets, both-teams-to-score and over 2.5 rates, shots, corners, cards, form and "
        "current streak. Use for questions about how a team usually performs, at home or away.",
        {
            "team": _TEAM,
            "venue": {"type": "string", "enum": ["all", "home", "away"], "description": "Which matches to count"},
            "seasons": {"type": "integer", "description": "How many recent seasons to include (1-10)"},
        },
    ),
    _tool(
        "get_league_table_history",
        "The Premier League table for a season (any season since 1993/94). Use for questions about final "
        "positions, title races or relegation in a past or the current season.",
        {"season": {"type": "string", "description": "Season like '2024/25', or an empty string for the latest"}},
    ),
]

FOREX_TOOL = _tool(
    "get_forex_signal",
    "Get the hourly technical-analysis signal (buy/sell/neutral, strength, price, indicators) for a currency "
    "pair. Supported: EUR/USD, GBP/USD, USD/JPY, AUD/USD, USD/KES. Educational analysis only.",
    {"pair": {"type": "string", "description": "Pair such as 'EUR/USD' or 'usdkes', or an empty string for all pairs"}},
)


def tool_definitions(forex_enabled: bool) -> list[dict[str, Any]]:
    tools = [*SPORTS_TOOLS, *HISTORY_TOOLS]
    return [*tools, FOREX_TOOL] if forex_enabled else tools


@dataclass
class ToolOutcome:
    content: str
    is_error: bool = False
    teams: list[Team] = field(default_factory=list)
    predictions: list[Prediction] = field(default_factory=list)
    pairs: list[CurrencyPair] = field(default_factory=list)
    signals: list[ForexSignal] = field(default_factory=list)
    used_sports_data: bool = False
    used_forex_data: bool = False


def _ok(data: dict[str, Any], **kwargs: Any) -> ToolOutcome:
    return ToolOutcome(content=json.dumps(data, ensure_ascii=False, sort_keys=True), **kwargs)


def _error(message: str) -> ToolOutcome:
    return ToolOutcome(content=json.dumps({"error": message}, ensure_ascii=False), is_error=True)


class ToolExecutor:
    def __init__(
        self,
        sports: SportsService,
        predictions: PredictionEngine,
        forex: ForexSignalEngine,
        forex_enabled: bool = True,
    ) -> None:
        self.sports = sports
        self.predictions = predictions
        self.forex = forex
        self.forex_enabled = forex_enabled
        self.history: HistoryService | None = None  # set by the container once storage exists

    async def execute(self, name: str, tool_input: dict[str, Any]) -> ToolOutcome:
        handlers = {
            "get_upcoming_fixtures": self._fixtures,
            "get_match_prediction": self._prediction,
            "get_team_form": self._team_form,
            "get_head_to_head": self._head_to_head,
            "get_forex_signal": self._forex_signal,
            "get_head_to_head_history": self._h2h_history,
            "get_team_history_stats": self._team_history_stats,
            "get_league_table_history": self._league_table_history,
        }
        handler = handlers.get(name)
        if handler is None or (name == "get_forex_signal" and not self.forex_enabled):
            return _error(f"Unknown tool {name}")
        args = {k: str(v).strip()[:100] for k, v in (tool_input or {}).items()}
        try:
            return await handler(**args)
        except TypeError:
            return _error(f"Invalid arguments for {name}")
        except (UnknownTeamError, ValueError) as exc:
            return _error(f"Unknown team or season '{exc}' in the historical data")
        except HistoryUnavailableError:
            return _error("Historical match data is not loaded")
        except (SportsDataError, ForexDataError, InsufficientDataError, InsufficientForexDataError) as exc:
            logger.warning("tool_data_unavailable", extra={"tool": name, "error": str(exc)})
            return _error("Data is temporarily unavailable")

    async def _team(self, text: str) -> Team | None:
        teams = await self.sports.find_teams(text)
        return teams[0] if teams else None

    async def _unknown_team(self, text: str) -> ToolOutcome:
        known = sorted(t.name for t in await self.sports.provider.list_teams())
        return _error(f"Unknown team '{text}'. Known teams: {', '.join(known)}")

    def _freshness(self, provider_simulated: bool) -> dict[str, Any]:
        return {"data_is_simulated": provider_simulated}

    async def _fixtures(self, team: str = "") -> ToolOutcome:
        found = await self._team(team) if team else None
        if team and found is None:
            return await self._unknown_team(team)
        fixtures = await self.sports.upcoming_fixtures(limit=6, team=found)
        return _ok(
            {
                "fixtures": [
                    {
                        "match_id": f.match_id,
                        "competition": f.competition,
                        "home_team": f.home_team.name,
                        "away_team": f.away_team.name,
                        "kickoff_utc": f.kickoff.isoformat(),
                    }
                    for f in fixtures
                ],
                **self._freshness(self.sports.provider.is_simulated),
            },
            teams=[found] if found else [],
            used_sports_data=True,
        )

    async def _prediction(self, team_a: str = "", team_b: str = "") -> ToolOutcome:
        a, b = await self._team(team_a), await self._team(team_b)
        if a is None:
            return await self._unknown_team(team_a)
        if b is None:
            return await self._unknown_team(team_b)
        fixture = await self.sports.fixture_between(a, b)
        if fixture is None:
            return _error(f"No scheduled match between {a.name} and {b.name}. Do not predict one.")
        p = await self.predictions.predict_fixture(fixture)
        return _ok(
            {
                "match_id": p.match_id,
                "competition": p.competition,
                "home_team": p.home_team,
                "away_team": p.away_team,
                "kickoff_utc": p.kickoff.isoformat(),
                "home_win_pct": round(p.probabilities.home_win * 100),
                "draw_pct": round(p.probabilities.draw * 100),
                "away_win_pct": round(p.probabilities.away_win * 100),
                "expected_goals_home": p.expected_goals.home,
                "expected_goals_away": p.expected_goals.away,
                "key_factors": p.key_factors,
                "model_version": p.model_version,
                "note": "Probabilities are estimates, not guarantees.",
                **self._freshness(p.freshness.is_simulated),
            },
            teams=[a, b],
            predictions=[p],
            used_sports_data=True,
        )

    async def _team_form(self, team: str = "") -> ToolOutcome:
        found = await self._team(team)
        if found is None:
            return await self._unknown_team(team)
        results = await self.sports.provider.get_results(team_id=found.team_id)
        recent = await self.sports.recent_results(found, limit=3)
        upcoming = await self.sports.upcoming_fixtures(limit=1, team=found)
        return _ok(
            {
                "team": found.name,
                "form_latest_first": team_form(results, found.team_id) or None,
                "recent_results": [
                    {
                        "home_team": r.home_team.name,
                        "away_team": r.away_team.name,
                        "score": f"{r.home_goals}-{r.away_goals}",
                        "date": r.kickoff.date().isoformat(),
                    }
                    for r in recent
                ],
                "next_fixture": (
                    {
                        "home_team": upcoming[0].home_team.name,
                        "away_team": upcoming[0].away_team.name,
                        "kickoff_utc": upcoming[0].kickoff.isoformat(),
                    }
                    if upcoming
                    else None
                ),
                **self._freshness(self.sports.provider.is_simulated),
            },
            teams=[found],
            used_sports_data=True,
        )

    async def _head_to_head(self, team_a: str = "", team_b: str = "") -> ToolOutcome:
        a, b = await self._team(team_a), await self._team(team_b)
        if a is None:
            return await self._unknown_team(team_a)
        if b is None:
            return await self._unknown_team(team_b)
        result = await self.sports.last_meeting(a, b)
        if result is None:
            return _error(f"No recorded match between {a.name} and {b.name}.")
        return _ok(
            {
                "home_team": result.home_team.name,
                "away_team": result.away_team.name,
                "score": f"{result.home_goals}-{result.away_goals}",
                "date": result.kickoff.date().isoformat(),
                **self._freshness(self.sports.provider.is_simulated),
            },
            teams=[a, b],
            used_sports_data=True,
        )

    def _history_service(self) -> HistoryService:
        if self.history is None or not self.history.loaded:
            raise HistoryUnavailableError
        return self.history

    async def _h2h_history(self, team_a: str = "", team_b: str = "") -> ToolOutcome:
        h2h = self._history_service().head_to_head(team_a, team_b, recent=6)
        return _ok({**h2h.model_dump(mode="json"), "competition": "Premier League", "data_is_simulated": False})

    async def _team_history_stats(self, team: str = "", venue: str = "all", seasons: str = "3") -> ToolOutcome:
        n = max(1, min(10, int(seasons) if seasons.isdigit() else 3))
        stats = self._history_service().team_stats(team, seasons=n, venue=venue if venue in ("home", "away") else "all")
        return _ok({**stats.model_dump(mode="json"), "competition": "Premier League", "data_is_simulated": False})

    async def _league_table_history(self, season: str = "") -> ToolOutcome:
        table = self._history_service().league_table(parse_season(season) if season else None)
        data = table.model_dump(mode="json")
        return _ok({**data, "competition": "Premier League", "data_is_simulated": False})

    async def _forex_signal(self, pair: str = "") -> ToolOutcome:
        if pair:
            pairs = await self.forex.find_pairs(pair)
            if not pairs:
                try:
                    signals = [await self.forex.signal(pair)]
                except PairNotFoundError:
                    supported = ", ".join(p.display_name for p in await self.forex.provider.list_pairs())
                    return _error(f"Unsupported pair '{pair}'. Supported: {supported}")
            else:
                signals = [await self.forex.signal(p.symbol) for p in pairs[:3]]
        else:
            signals = await self.forex.signals()
        return _ok(
            {
                "signals": [
                    {
                        "pair": s.display_name,
                        "timeframe": s.timeframe,
                        "direction": s.direction.value,
                        "strength": s.strength.value,
                        "price": s.price,
                        "stop_loss": s.stop_loss,
                        "take_profit": s.take_profit,
                        "key_factors": s.key_factors,
                    }
                    for s in signals
                ],
                "trade_levels_enabled": self.forex.trade_levels_enabled,
                "note": "Educational technical analysis, not financial advice. Strength is indicator agreement, "
                "not a win probability.",
                **self._freshness(self.forex.provider.is_simulated),
            },
            pairs=[p for p in await self.forex.provider.list_pairs() if p.symbol in {s.symbol for s in signals}],
            signals=signals,
            used_forex_data=True,
        )
