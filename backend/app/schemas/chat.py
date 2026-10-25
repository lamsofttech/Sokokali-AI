"""Chat request/response contracts."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

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
    GUARANTEE_REQUEST = "guarantee_request"
    HELP = "help"
    MODERATED = "moderated"
    UNKNOWN = "unknown"


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000, examples=["Sokokali, Arsenal na Chelsea nani atashinda?"])
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
    is_simulated_data: bool
    moderated: bool = False
    responded_at: datetime
