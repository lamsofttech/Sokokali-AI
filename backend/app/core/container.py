"""Builds and holds the application's service graph (simple dependency injection)."""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.core.config import Settings
from app.core.rate_limit import SlidingWindowRateLimiter
from app.integrations.sports.base import SportsDataProvider
from app.integrations.sports.simulated import SimulatedSportsProvider
from app.services.ai_engine import SokokaliAI
from app.services.chat_service import ChatService
from app.services.conversation_memory import ConversationMemory
from app.services.prediction_engine import PredictionEngine
from app.services.sports_engine import SportsService


@dataclass
class Container:
    settings: Settings
    sports_provider: SportsDataProvider
    sports: SportsService
    predictions: PredictionEngine
    ai: SokokaliAI
    memory: ConversationMemory
    chat: ChatService
    chat_rate_limiter: SlidingWindowRateLimiter
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))


def build_sports_provider(settings: Settings) -> SportsDataProvider:
    if settings.sports_provider == "simulated":
        return SimulatedSportsProvider(seed=settings.simulation_seed)
    raise ValueError(f"Unsupported sports provider: {settings.sports_provider}")


def build_container(settings: Settings, sports_provider: SportsDataProvider | None = None) -> Container:
    provider = sports_provider or build_sports_provider(settings)
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
    return Container(
        settings=settings,
        sports_provider=provider,
        sports=sports,
        predictions=predictions,
        ai=ai,
        memory=memory,
        chat=ChatService(ai, sports, predictions, memory),
        chat_rate_limiter=SlidingWindowRateLimiter(settings.chat_rate_limit_per_minute, 60.0),
    )
