"""Chat orchestration: moderate -> understand -> fetch verified data -> reply -> remember."""

import logging
import time
from datetime import UTC, datetime

from app.integrations.sports.base import SportsDataError
from app.schemas.chat import ChatRequest, ChatResponse, Intent, Language
from app.schemas.sports import Prediction, Team
from app.services.ai_engine import SokokaliAI
from app.services.conversation_memory import ConversationMemory, Turn
from app.services.prediction_engine import InsufficientDataError, PredictionEngine, team_form
from app.services.sports_engine import SportsService

logger = logging.getLogger(__name__)

ANONYMOUS_VIEWER = "anonymous"


class ChatService:
    def __init__(
        self,
        ai: SokokaliAI,
        sports: SportsService,
        predictions: PredictionEngine,
        memory: ConversationMemory,
    ) -> None:
        self.ai = ai
        self.sports = sports
        self.predictions = predictions
        self.memory = memory

    async def handle(self, request: ChatRequest) -> ChatResponse:
        viewer_id = request.viewer_id or ANONYMOUS_VIEWER
        teams = await self.sports.find_teams(request.message)
        analysis = self.ai.analyze(request.message, len(teams), request.language)
        language, intent = analysis.language, analysis.intent

        # Follow-up questions ("na nani atashinda?") reuse the teams from earlier in the conversation.
        if not teams and intent in (Intent.PREDICTION, Intent.RESULTS, Intent.TEAM_FORM) and request.viewer_id:
            teams = await self._teams_by_id(self.memory.last_team_ids(viewer_id))

        prediction: Prediction | None = None
        uses_sports_data = False
        if intent == Intent.MODERATED:
            reply = self.ai.compose(f"moderated_{analysis.moderation_reason}", language)
            logger.info("chat_moderated", extra={"reason": analysis.moderation_reason, "viewer": viewer_id})
        elif intent == Intent.PREDICTION:
            reply, prediction, uses_sports_data = await self._prediction_reply(teams, language)
        elif intent == Intent.FIXTURES:
            reply, uses_sports_data = await self._fixtures_reply(teams, language)
        elif intent == Intent.RESULTS:
            reply, uses_sports_data = await self._results_reply(teams, language)
        elif intent == Intent.TEAM_FORM:
            reply, uses_sports_data = await self._form_reply(teams, language)
        else:
            key = {Intent.GREETING: "greeting", Intent.GUARANTEE_REQUEST: "guarantee", Intent.HELP: "help"}
            reply = self.ai.compose(key.get(intent, "unknown"), language)

        is_simulated = uses_sports_data and self.sports.provider.is_simulated
        if is_simulated:
            reply = f"{reply} {self.ai.compose('simulated_notice', language)}"

        if intent != Intent.MODERATED:  # never retain abusive messages or personal data
            self.memory.add(
                viewer_id,
                Turn(request.message, reply, intent, tuple(t.team_id for t in teams), time.monotonic()),
            )

        return ChatResponse(
            reply=reply,
            language=language,
            intent=intent,
            teams=[t.name for t in teams],
            prediction=prediction,
            is_simulated_data=is_simulated,
            moderated=intent == Intent.MODERATED,
            responded_at=datetime.now(UTC),
        )

    async def _teams_by_id(self, team_ids: tuple[str, ...]) -> list[Team]:
        if not team_ids:
            return []
        by_id = {t.team_id: t for t in await self.sports.provider.list_teams()}
        return [by_id[i] for i in team_ids if i in by_id]

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
