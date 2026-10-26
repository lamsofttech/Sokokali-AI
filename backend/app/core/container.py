"""Builds and holds the application's service graph (simple dependency injection)."""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import anthropic

from app.core.config import Settings
from app.core.rate_limit import SlidingWindowRateLimiter
from app.integrations.forex.base import ForexDataProvider
from app.integrations.forex.simulated import SimulatedForexProvider
from app.integrations.live.base import LiveEventSource
from app.integrations.live.simulated import SimulatedLiveSource, Topics
from app.integrations.live.tiktok import TikTokLiveSource
from app.integrations.sports.base import SportsDataError, SportsDataProvider
from app.integrations.sports.football_data import FootballDataProvider
from app.integrations.sports.simulated import SimulatedSportsProvider
from app.services.ai_engine import SokokaliAI
from app.services.broadcast_controller import BroadcastController
from app.services.chat_service import ChatService
from app.services.compliance import ComplianceService
from app.services.conversation_memory import ConversationMemory
from app.services.forex_engine import ForexSignalEngine
from app.services.gamification import GamificationEngine
from app.services.live_hub import LiveHub
from app.services.live_pipeline import LiveEventPipeline
from app.services.llm_engine import AnthropicLLMEngine
from app.services.llm_tools import ToolExecutor
from app.services.prediction_engine import PredictionEngine
from app.services.sports_engine import SportsService


@dataclass
class Container:
    settings: Settings
    sports_provider: SportsDataProvider
    sports: SportsService
    predictions: PredictionEngine
    forex_provider: ForexDataProvider
    forex: ForexSignalEngine
    ai: SokokaliAI
    memory: ConversationMemory
    chat: ChatService
    chat_rate_limiter: SlidingWindowRateLimiter
    hub: LiveHub
    gamification: GamificationEngine
    broadcast: BroadcastController
    llm: AnthropicLLMEngine | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    async def aclose(self) -> None:
        await self.broadcast.stop()
        if self.llm is not None:
            await self.llm.aclose()
        await self.sports_provider.aclose()
        await self.forex_provider.aclose()


logger = logging.getLogger(__name__)


def build_sports_provider(settings: Settings) -> SportsDataProvider:
    if settings.sports_provider == "simulated":
        return SimulatedSportsProvider(seed=settings.simulation_seed)
    if settings.sports_provider == "football_data":
        key = settings.football_data_api_key.get_secret_value().strip() if settings.football_data_api_key else ""
        if not key:
            raise ValueError("SOKOKALI_SPORTS_PROVIDER=football_data needs FOOTBALL_DATA_API_KEY in .env")
        return FootballDataProvider(
            api_key=key,
            competitions=settings.football_data_competitions,
            base_url=settings.football_data_base_url,
            seasons_of_history=settings.football_data_seasons_of_history,
            cache_ttl_seconds=settings.sports_cache_ttl_seconds,
            timeout_seconds=settings.http_timeout_seconds,
            max_attempts=settings.http_max_attempts,
        )
    raise ValueError(f"Unsupported sports provider: {settings.sports_provider}")


def build_forex_provider(settings: Settings) -> ForexDataProvider:
    if settings.forex_provider == "simulated":
        return SimulatedForexProvider(seed=settings.simulation_seed)
    raise ValueError(f"Unsupported forex provider: {settings.forex_provider}")


def build_llm_client(settings: Settings) -> Any | None:
    """An AsyncAnthropic client, or None when the LLM is switched off or has no credentials."""
    key = (settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else "").strip() or None
    if settings.llm_provider == "none" or (settings.llm_provider == "auto" and not key):
        return None
    try:
        return anthropic.AsyncAnthropic(
            api_key=key, timeout=settings.llm_timeout_seconds, max_retries=settings.llm_max_retries
        )
    except anthropic.AnthropicError as exc:  # e.g. no credentials found for provider "anthropic"
        logger.warning("llm_client_unavailable", extra={"error": str(exc)})
        return None


def build_live_source(settings: Settings, sports: SportsService, forex_provider: ForexDataProvider) -> LiveEventSource:
    if settings.live_source == "tiktok":
        return TikTokLiveSource()

    async def topics() -> Topics:
        try:
            fixtures = await sports.upcoming_fixtures(limit=10)
        except SportsDataError:
            fixtures = []
        pairs = [p.display_name for p in await forex_provider.list_pairs()] if settings.forex_enabled else []
        return Topics(matches=[(f.home_team.name, f.away_team.name) for f in fixtures], pairs=pairs)

    return SimulatedLiveSource(topics, events_per_second=settings.live_sim_events_per_second)


def build_container(
    settings: Settings,
    sports_provider: SportsDataProvider | None = None,
    forex_provider: ForexDataProvider | None = None,
    llm_client: Any | None = None,
    live_source: LiveEventSource | None = None,
    autoloop: bool = True,
) -> Container:
    provider = sports_provider or build_sports_provider(settings)
    fx_provider = forex_provider or build_forex_provider(settings)
    forex = ForexSignalEngine(
        fx_provider,
        model_version=settings.forex_signal_model_version,
        trade_levels_enabled=settings.forex_trade_levels_enabled,
    )
    sports = SportsService(provider)
    predictions = PredictionEngine(
        provider,
        model_version=settings.prediction_model_version,
        poisson_weight=settings.prediction_poisson_weight,
        min_history_matches=settings.prediction_min_history_matches,
    )
    ai = SokokaliAI()
    memory = ConversationMemory(
        max_turns=settings.conversation_history_turns, ttl_seconds=settings.conversation_ttl_seconds
    )
    client = llm_client if llm_client is not None else build_llm_client(settings)
    llm = (
        AnthropicLLMEngine(
            client,
            ToolExecutor(sports, predictions, forex, forex_enabled=settings.forex_enabled),
            model=settings.llm_model,
            effort=settings.llm_effort,
            max_tokens=settings.llm_max_tokens,
            max_tool_rounds=settings.llm_max_tool_rounds,
            forex_enabled=settings.forex_enabled,
        )
        if client is not None
        else None
    )
    chat = ChatService(
        ai,
        sports,
        predictions,
        forex,
        memory,
        forex_enabled=settings.forex_enabled,
        llm=llm,
        llm_history_turns=settings.llm_history_turns,
    )
    hub = LiveHub()
    gamification = GamificationEngine()
    broadcast = BroadcastController(
        live_source or build_live_source(settings, sports, fx_provider),
        LiveEventPipeline(
            ai,
            sports,
            forex,
            max_queue=settings.live_max_queue,
            dedup_ttl_seconds=settings.live_dedup_ttl_seconds,
            comments_per_viewer_per_minute=settings.live_comments_per_viewer_per_minute,
            max_comment_age_seconds=settings.live_max_comment_age_seconds,
        ),
        gamification,
        chat,
        sports,
        ComplianceService(settings.compliance_jurisdiction, settings.compliance_min_age),
        hub,
        forex_enabled=settings.forex_enabled,
        words_per_second=settings.live_words_per_second,
        min_gap_seconds=settings.live_min_gap_seconds,
        segment_interval_seconds=settings.live_segment_interval_seconds,
        segment_max_gap_seconds=settings.live_segment_max_gap_seconds,
        trivia_seconds=settings.live_trivia_seconds,
        poll_seconds=settings.live_poll_seconds,
        autoloop=autoloop,
    )
    return Container(
        settings=settings,
        sports_provider=provider,
        sports=sports,
        predictions=predictions,
        forex_provider=fx_provider,
        forex=forex,
        ai=ai,
        memory=memory,
        chat=chat,
        hub=hub,
        gamification=gamification,
        broadcast=broadcast,
        llm=llm,
        chat_rate_limiter=SlidingWindowRateLimiter(settings.chat_rate_limit_per_minute, 60.0),
    )
