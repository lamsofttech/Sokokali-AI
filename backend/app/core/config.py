"""Environment-based configuration for Sokokali.

Every setting can be overridden with an environment variable prefixed with
``SOKOKALI_`` (for example ``SOKOKALI_LOG_LEVEL=DEBUG``) or through a ``.env``
file in the repository root or the ``backend`` directory.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SOKOKALI_",
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Sokokali"
    app_version: str = "0.4.0"
    environment: Literal["development", "test", "staging", "production"] = "development"

    log_level: str = "INFO"
    log_json: bool = True

    # Browser origins allowed to call the API (the Phase 4 dashboard runs on Vite's port).
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    # Sports data.
    #   simulated     - offline synthetic data (default)
    #   football_data - real data from football-data.org (needs FOOTBALL_DATA_API_KEY)
    sports_provider: Literal["simulated", "football_data"] = "simulated"
    simulation_seed: int = 2024
    football_data_api_key: SecretStr | None = Field(default=None, validation_alias="FOOTBALL_DATA_API_KEY")
    football_data_base_url: str = "https://api.football-data.org/v4"
    # JSON list of competition codes, e.g. ["PL"] or ["PL","PD"]; the free tier covers the major leagues.
    football_data_competitions: list[str] = Field(default_factory=lambda: ["PL"])
    football_data_seasons_of_history: int = Field(2, ge=1, le=5)
    sports_cache_ttl_seconds: int = Field(300, ge=10)
    http_timeout_seconds: float = Field(10.0, gt=0)
    http_max_attempts: int = Field(3, ge=1, le=6)

    # Prediction model.
    prediction_model_version: str = "poisson-elo-blend-0.1.0"
    prediction_poisson_weight: float = Field(0.7, ge=0.0, le=1.0)
    prediction_min_history_matches: int = Field(10, ge=1)

    # Forex. Only the simulated provider exists so far.
    forex_enabled: bool = True
    forex_provider: Literal["simulated"] = "simulated"
    forex_signal_model_version: str = "fx-technical-0.1.0"
    # Publishing entry/stop-loss/take-profit levels to the public may be regulated investment advice
    # (in Kenya, the Capital Markets Authority licenses investment advisers). Keep this false until a
    # licensing/legal review approves it.
    forex_trade_levels_enabled: bool = False

    # Conversational LLM (Phase 2).
    #   auto      - use Anthropic Claude when ANTHROPIC_API_KEY is set, otherwise the rule-based engine
    #   anthropic - always use Claude (the SDK also accepts `ant auth login` profiles)
    #   none      - rule-based engine only (offline)
    llm_provider: Literal["auto", "anthropic", "none"] = "auto"
    anthropic_api_key: SecretStr | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    llm_model: str = "claude-opus-5-5"
    llm_effort: Literal["low", "medium", "high", "xhigh", "max"] = "low"
    llm_max_tokens: int = Field(16000, ge=256)
    llm_timeout_seconds: float = Field(30.0, gt=0)
    llm_max_retries: int = Field(2, ge=0, le=10)
    llm_max_tool_rounds: int = Field(4, ge=1, le=10)
    llm_history_turns: int = Field(6, ge=0, le=50)

    # Chat.
    chat_max_message_length: int = Field(500, ge=1, le=2000)
    conversation_history_turns: int = Field(10, ge=1, le=100)
    conversation_ttl_seconds: int = Field(1800, ge=60)
    chat_rate_limit_per_minute: int = Field(30, ge=1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
