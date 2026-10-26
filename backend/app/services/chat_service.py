"""Chat orchestration: moderate -> understand -> fetch verified data -> reply -> remember.

Covers two markets: football (fixtures, results, predictions) and forex (technical signals).
"""

import logging
import time
from collections.abc import Callable, Hashable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from app.integrations.forex.base import ForexDataError
from app.integrations.sports.base import SportsDataError
from app.schemas.chat import ChatRequest, ChatResponse, Intent, Language
from app.schemas.forex import CurrencyPair, ForexSignal
from app.schemas.sports import Prediction, Team
from app.services.ai_engine import SokokaliAI
from app.services.conversation_memory import ConversationMemory, Turn
from app.services.forex_engine import ForexSignalEngine, InsufficientForexDataError
from app.services.llm_engine import AnthropicLLMEngine, HistoryTurn, LLMUnavailableError
from app.services.prediction_engine import InsufficientDataError, PredictionEngine, team_form
from app.services.speech_service import build_speech_cue
from app.services.sports_engine import SportsService

logger = logging.getLogger(__name__)

ANONYMOUS_VIEWER = "anonymous"


def _unique[T](items: list[T], key: Callable[[T], Hashable]) -> list[T]:
    seen: set[Hashable] = set()
    out = []
    for item in items:
        if key(item) not in seen:
            seen.add(key(item))
            out.append(item)
    return out


@dataclass
class _Draft:
    """A reply plus the data behind it, before notices are added."""

    reply: str
    intent: Intent
    teams: list[Team]
    pairs: list[CurrencyPair]
    prediction: Prediction | None = None
    signals: list[ForexSignal] = field(default_factory=list)
    uses_sports_data: bool = False
    uses_forex_data: bool = False
    engine: Literal["llm", "rules"] = "rules"


class ChatService:
    def __init__(
        self,
        ai: SokokaliAI,
        sports: SportsService,
        predictions: PredictionEngine,
        forex: ForexSignalEngine,
        memory: ConversationMemory,
        forex_enabled: bool = True,
        llm: AnthropicLLMEngine | None = None,
        llm_history_turns: int = 6,
    ) -> None:
        self.ai = ai
        self.sports = sports
        self.predictions = predictions
        self.forex = forex
        self.memory = memory
        self.forex_enabled = forex_enabled
        self.llm = llm
        self.llm_history_turns = llm_history_turns

    async def handle(self, request: ChatRequest) -> ChatResponse:
        viewer_id = request.viewer_id or ANONYMOUS_VIEWER
        try:
            teams = await self.sports.find_teams(request.message)
        except SportsDataError as exc:
            logger.warning("team_lookup_unavailable", extra={"error": str(exc)})
            teams = []
        pairs = await self.forex.find_pairs(request.message)
        analysis = self.ai.analyze(request.message, len(teams), request.language, len(pairs))
        language, intent = analysis.language, analysis.intent

        # Follow-up questions ("na nani atashinda?") reuse the teams from earlier in the conversation.
        if not teams and intent in (Intent.PREDICTION, Intent.RESULTS, Intent.TEAM_FORM) and request.viewer_id:
            teams = await self._teams_by_id(self.memory.last_team_ids(viewer_id))

        draft: _Draft | None = None
        # Moderation and "guarantee" requests always get the deterministic answer; everything else goes to
        # Claude when it is configured, with the rule-based engine as the fallback.
        if intent not in (Intent.MODERATED, Intent.GUARANTEE_REQUEST) and self.llm is not None and self.llm.available:
            draft = await self._llm_draft(request, viewer_id, language, intent, teams, pairs)
        if draft is None:
            draft = await self._rules_draft(request, analysis.moderation_reason, language, intent, teams, pairs)

        is_simulated = (draft.uses_sports_data and self.sports.provider.is_simulated) or (
            draft.uses_forex_data and self.forex.provider.is_simulated
        )
        reply = draft.reply
        if is_simulated:
            reply = f"{reply} {self.ai.compose('simulated_notice', language)}"

        if draft.intent != Intent.MODERATED:  # never retain abusive messages or personal data
            self.memory.add(
                viewer_id,
                Turn(request.message, reply, draft.intent, tuple(t.team_id for t in draft.teams), time.monotonic()),
            )

        return ChatResponse(
            reply=reply,
            language=language,
            intent=draft.intent,
            teams=[t.name for t in draft.teams],
            prediction=draft.prediction,
            currency_pairs=[p.display_name for p in draft.pairs],
            forex_signals=draft.signals,
            is_simulated_data=is_simulated,
            moderated=draft.intent == Intent.MODERATED,
            engine=draft.engine,
            speech=build_speech_cue(reply, language, draft.intent, is_simulated),
            responded_at=datetime.now(UTC),
        )

    async def _llm_draft(
        self,
        request: ChatRequest,
        viewer_id: str,
        language: Language,
        intent: Intent,
        teams: list[Team],
        pairs: list[CurrencyPair],
    ) -> _Draft | None:
        assert self.llm is not None
        history = (
            [HistoryTurn(t.message, t.reply) for t in self.memory.history(viewer_id)][-self.llm_history_turns :]
            if request.viewer_id and self.llm_history_turns
            else []
        )
        try:
            result = await self.llm.respond(request.message, language, history)
        except LLMUnavailableError as exc:
            logger.info("llm_fallback_to_rules", extra={"reason": str(exc)})
            return None
        outcomes = [o for o in result.outcomes if not o.is_error]
        predictions = [p for o in outcomes for p in o.predictions]
        signals = [s for o in outcomes for s in o.signals]
        reply = result.reply
        if predictions:
            reply += " " + self.ai.compose("prediction_disclaimer", language)
        if signals:
            reply += " " + self.ai.compose("forex_risk", language)
        return _Draft(
            reply=reply,
            intent=Intent.PREDICTION if predictions else Intent.FOREX if signals else intent,
            teams=_unique(teams + [t for o in outcomes for t in o.teams], key=lambda t: t.team_id),
            pairs=_unique(pairs + [p for o in outcomes for p in o.pairs], key=lambda p: p.symbol),
            prediction=predictions[0] if predictions else None,
            signals=signals,
            uses_sports_data=any(o.used_sports_data for o in outcomes),
            uses_forex_data=any(o.used_forex_data for o in outcomes),
            engine="llm",
        )

    async def _rules_draft(
        self,
        request: ChatRequest,
        moderation_reason: str | None,
        language: Language,
        intent: Intent,
        teams: list[Team],
        pairs: list[CurrencyPair],
    ) -> _Draft:
        draft = _Draft(reply="", intent=intent, teams=teams, pairs=pairs)
        if intent == Intent.MODERATED:
            draft.reply = self.ai.compose(f"moderated_{moderation_reason}", language)
            logger.info("chat_moderated", extra={"reason": moderation_reason, "viewer": request.viewer_id})
        elif intent == Intent.FOREX:
            draft.reply, draft.signals, draft.uses_forex_data = await self._forex_reply(pairs, language)
        elif intent == Intent.GUARANTEE_REQUEST and self.ai.mentions_forex(request.message, len(pairs)):
            draft.reply = self.ai.compose("guarantee_forex", language)
        elif intent == Intent.PREDICTION:
            draft.reply, draft.prediction, draft.uses_sports_data = await self._prediction_reply(teams, language)
        elif intent == Intent.FIXTURES:
            draft.reply, draft.uses_sports_data = await self._fixtures_reply(teams, language)
        elif intent == Intent.RESULTS:
            draft.reply, draft.uses_sports_data = await self._results_reply(teams, language)
        elif intent == Intent.TEAM_FORM:
            draft.reply, draft.uses_sports_data = await self._form_reply(teams, language)
        else:
            key = {Intent.GREETING: "greeting", Intent.GUARANTEE_REQUEST: "guarantee", Intent.HELP: "help"}
            draft.reply = self.ai.compose(key.get(intent, "unknown"), language)
        return draft

    async def _teams_by_id(self, team_ids: tuple[str, ...]) -> list[Team]:
        if not team_ids:
            return []
        by_id = {t.team_id: t for t in await self.sports.provider.list_teams()}
        return [by_id[i] for i in team_ids if i in by_id]

    async def _forex_reply(
        self, pairs: list[CurrencyPair], language: Language
    ) -> tuple[str, list[ForexSignal], bool]:
        if not self.forex_enabled:
            return self.ai.compose("forex_disabled", language), [], False
        symbols = [p.symbol for p in pairs[:3]] or [p.symbol for p in await self.forex.provider.list_pairs()]
        try:
            signals = [await self.forex.signal(symbol) for symbol in symbols]
        except (ForexDataError, InsufficientForexDataError) as exc:
            logger.warning("forex_signal_unavailable", extra={"symbols": symbols, "error": str(exc)})
            name = pairs[0].display_name if pairs else "forex"
            return self.ai.compose("forex_unavailable", language, pair=name), [], False
        risk = self.ai.compose("forex_risk", language)
        if len(signals) == 1:
            signal = signals[0]
            levels = ""
            if signal.stop_loss is not None and signal.take_profit is not None:
                levels = self.ai.compose(
                    "forex_levels", language, stop_loss=signal.stop_loss, take_profit=signal.take_profit
                )
            reply = self.ai.compose(
                "forex_signal",
                language,
                pair=signal.display_name,
                direction=self.ai.format_direction(signal.direction, language),
                strength=self.ai.format_strength(signal.strength, language),
                price=signal.price,
                levels=levels,
                risk=risk,
            )
            return reply, signals, True
        lines = [
            f"{s.display_name} {self.ai.format_direction(s.direction, language, with_hint=False)} "
            f"({self.ai.format_strength(s.strength, language)})"
            for s in signals
        ]
        reply = f"{self.ai.compose('forex_overview_header', language)} " + "; ".join(lines) + f". {risk}"
        return reply, signals, True

    async def _prediction_reply(self, teams: list[Team], language: Language) -> tuple[str, Prediction | None, bool]:
        if len(teams) < 2:
            return self.ai.compose("need_two_teams", language), None, False
        team_a, team_b = teams[0], teams[1]
        fixture = await self.sports.fixture_between(team_a, team_b)
        if fixture is None:
            return self.ai.compose("no_fixture", language, team_a=team_a.name, team_b=team_b.name), None, False
        try:
            prediction = await self.predictions.predict_fixture(fixture)
        except (InsufficientDataError, SportsDataError) as exc:
            logger.warning("prediction_unavailable", extra={"match_id": fixture.match_id, "error": str(exc)})
            reply = self.ai.compose(
                "prediction_unavailable", language, home=fixture.home_team.name, away=fixture.away_team.name
            )
            return reply, None, False
        probs = prediction.probabilities
        reply = self.ai.compose(
            "prediction",
            language,
            home=prediction.home_team,
            away=prediction.away_team,
            competition=prediction.competition,
            kickoff=self.ai.format_kickoff(prediction.kickoff, language),
            home_p=self.ai.format_percent(probs.home_win),
            draw_p=self.ai.format_percent(probs.draw),
            away_p=self.ai.format_percent(probs.away_win),
            home_xg=f"{prediction.expected_goals.home:.1f}",
            away_xg=f"{prediction.expected_goals.away:.1f}",
        )
        return reply, prediction, True

    async def _fixtures_reply(self, teams: list[Team], language: Language) -> tuple[str, bool]:
        fixtures = await self.sports.upcoming_fixtures(limit=5, team=teams[0] if teams else None)
        if not fixtures:
            return self.ai.compose("no_fixtures", language), False
        lines = [
            f"{f.home_team.name} vs {f.away_team.name} ({self.ai.format_kickoff(f.kickoff, language)})"
            for f in fixtures
        ]
        return f"{self.ai.compose('fixtures_header', language)} " + "; ".join(lines) + ".", True

    async def _results_reply(self, teams: list[Team], language: Language) -> tuple[str, bool]:
        if not teams:
            return self.ai.compose("need_team", language), False
        if len(teams) >= 2:
            result = await self.sports.last_meeting(teams[0], teams[1])
            if result is None:
                return self.ai.compose("no_result", language), False
            reply = self.ai.compose(
                "last_meeting",
                language,
                home=result.home_team.name,
                away=result.away_team.name,
                home_goals=result.home_goals,
                away_goals=result.away_goals,
                date=f"{result.kickoff:%d/%m/%Y}",
            )
            return reply, True
        results = await self.sports.recent_results(teams[0], limit=3)
        if not results:
            return self.ai.compose("no_result", language), False
        lines = [
            f"{r.home_team.name} {r.home_goals}-{r.away_goals} {r.away_team.name} ({r.kickoff:%d/%m})" for r in results
        ]
        return f"{self.ai.compose('recent_results_header', language, team=teams[0].name)} " + "; ".join(lines) + ".", True

    async def _form_reply(self, teams: list[Team], language: Language) -> tuple[str, bool]:
        if not teams:
            return self.ai.compose("need_team", language), False
        team = teams[0]
        form = team_form(await self.sports.provider.get_results(team_id=team.team_id), team.team_id)
        if not form:
            return self.ai.compose("no_result", language), False
        reply = self.ai.compose("team_form", language, team=team.name, form=form)
        upcoming = await self.sports.upcoming_fixtures(limit=1, team=team)
        if upcoming:
            f = upcoming[0]
            reply += " " + self.ai.compose(
                "next_fixture",
                language,
                home=f.home_team.name,
                away=f.away_team.name,
                kickoff=self.ai.format_kickoff(f.kickoff, language),
            )
        return reply, True
