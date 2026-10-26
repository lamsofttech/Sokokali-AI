"""Chat request/response contracts."""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.forex import ForexSignal
from app.schemas.speech import SpeechCue
from app.schemas.sports import Prediction


class Language(StrEnum):
    ENGLISH = "en"
    KISWAHILI = "sw"
    SHENG = "sheng"


class Intent(StrEnum):
    GREETING = "greeting"
    PREDICTION = "prediction"
    FIXTURES = "fixtures"
    RESULTS = "results"
    TEAM_FORM = "team_form"
    FOREX = "forex"
    GUARANTEE_REQUEST = "guarantee_request"
    HELP = "help"
    MODERATED = "moderated"
    UNKNOWN = "unknown"


class ChatRequest(BaseModel):
    message: str = Field(
        min_length=1,
        max_length=2000,
        examples=["Sokokali, Arsenal na Chelsea nani atashinda?", "EUR/USD signal"],
    )
    viewer_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9_.:-]+$",
        description="Opaque viewer identifier used for conversation context and rate limiting",
    )
    language: Language | None = Field(default=None, description="Force a reply language; auto-detected when omitted")


class ChatResponse(BaseModel):
    reply: str
    language: Language
    intent: Intent
    teams: list[str]
    prediction: Prediction | None = None
    currency_pairs: list[str] = Field(default_factory=list)
    forex_signals: list[ForexSignal] = Field(default_factory=list)
    is_simulated_data: bool
    moderated: bool = False
    engine: Literal["llm", "rules"] = Field(
        default="rules", description="Which engine wrote the reply: Claude (llm) or the offline rule-based engine"
    )
    speech: SpeechCue | None = Field(default=None, description="Cue for the avatar's voice and animation")
    responded_at: datetime
