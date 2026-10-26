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
from app.integrations.sports.base import SportsDataProvider
from app.integrations.sports.simulated import SimulatedSportsProvider
from app.services.ai_engine import SokokaliAI
from app.services.chat_service import ChatService
from app.services.conversation_memory import ConversationMemory
from app.services.forex_engine import ForexSignalEngine
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
    llm: AnthropicLLMEngine | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    async def aclose(self) -> None:
        if self.llm is not None:
            await self.llm.aclose()


logger = logging.getLogger(__name__)


def build_sports_provider(settings: Settings) -> SportsDataProvider:
    if settings.sports_provider == "simulated":
        return SimulatedSportsProvider(seed=settings.simulation_seed)
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


def build_container(
    settings: Settings,
    sports_provider: SportsDataProvider | None = None,
    forex_provider: ForexDataProvider | None = None,
    llm_client: Any | None = None,
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
    return Container(
        settings=settings,
        sports_provider=provider,
        sports=sports,
        predictions=predictions,
        forex_provider=fx_provider,
        forex=forex,
        ai=ai,
        memory=memory,
        chat=ChatService(
            ai,
            sports,
            predictions,
            forex,
            memory,
            forex_enabled=settings.forex_enabled,
            llm=llm,
            llm_history_turns=settings.llm_history_turns,
        ),
        llm=llm,
        chat_rate_limiter=SlidingWindowRateLimiter(settings.chat_rate_limit_per_minute, 60.0),
    )
