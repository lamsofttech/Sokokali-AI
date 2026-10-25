"""Environment-based configuration for Sokokali.

Every setting can be overridden with an environment variable prefixed with
``SOKOKALI_`` (for example ``SOKOKALI_LOG_LEVEL=DEBUG``) or through a ``.env``
file in the repository root or the ``backend`` directory.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SOKOKALI_",
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Sokokali"
    app_version: str = "0.2.0"
    environment: Literal["development", "test", "staging", "production"] = "development"

    log_level: str = "INFO"
    log_json: bool = True

    # Browser origins allowed to call the API (the Phase 4 dashboard runs on Vite's port).
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    # Sports data. Only the simulated provider exists in Phase 1.
    sports_provider: Literal["simulated"] = "simulated"
    simulation_seed: int = 2024

    # Prediction model.
    prediction_model_version: str = "poisson-elo-blend-0.1.0"
    prediction_poisson_weight: float = Field(0.7, ge=0.0, le=1.0)
    prediction_min_history_matches: int = Field(10, ge=1)

    # Chat.
    chat_max_message_length: int = Field(500, ge=1, le=2000)
    conversation_history_turns: int = Field(10, ge=1, le=100)
    conversation_ttl_seconds: int = Field(1800, ge=60)
    chat_rate_limit_per_minute: int = Field(30, ge=1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
