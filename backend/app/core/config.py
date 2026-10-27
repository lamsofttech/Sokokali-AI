"""Environment-based configuration for Sokokali.

Every setting can be overridden with an environment variable prefixed with
``SOKOKALI_`` (for example ``SOKOKALI_LOG_LEVEL=DEBUG``) or through a ``.env``
file in the repository root or the ``backend`` directory.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SOKOKALI_",
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Sokokali"
    app_version: str = "0.7.0"
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

    # Persistence (Phase 7). Both optional: without them Sokokali runs fully in memory.
    # e.g. postgresql+asyncpg://user:password@host:5432/sokokali  (sqlite+aiosqlite:///./sokokali.db also works)
    database_url: SecretStr | None = None
    # e.g. redis://localhost:6379/0 - shared rate limits across restarts and replicas
    redis_url: SecretStr | None = None
    gamification_snapshot_seconds: float = Field(30, ge=5)

    # Admin access for broadcast controls. Required outside development/test; send it as
    # "Authorization: Bearer <token>" (or ?token=<token> on the WebSocket).
    admin_token: SecretStr | None = None

    # Livestream (Phase 6).
    live_source: Literal["simulated", "tiktok"] = "simulated"
    live_sim_events_per_second: float = Field(0.6, gt=0, le=20)
    live_max_queue: int = Field(50, ge=1, le=1000)
    live_dedup_ttl_seconds: float = Field(60, gt=0)
    live_comments_per_viewer_per_minute: int = Field(4, ge=1, le=60)
    live_max_comment_age_seconds: float = Field(90, gt=0)
    live_words_per_second: float = Field(2.6, gt=0)
    live_min_gap_seconds: float = Field(2.0, ge=0)
    live_segment_interval_seconds: float = Field(45, ge=5)
    live_segment_max_gap_seconds: float = Field(180, ge=30)
    live_trivia_seconds: float = Field(30, ge=5)
    live_poll_seconds: float = Field(45, ge=5)

    # Responsible-gambling messaging (Module G).
    compliance_jurisdiction: str = "KE"
    compliance_min_age: int = Field(18, ge=18)

    # Chat.
    chat_max_message_length: int = Field(500, ge=1, le=2000)
    conversation_history_turns: int = Field(10, ge=1, le=100)
    conversation_ttl_seconds: int = Field(1800, ge=60)
    chat_rate_limit_per_minute: int = Field(30, ge=1)

    @field_validator("admin_token", "anthropic_api_key", "football_data_api_key", "database_url", "redis_url", mode="before")
    @classmethod
    def _blank_secret_is_unset(cls, value: object) -> object:
        # "KEY=" in .env means "not configured", not "the empty string is the secret".
        return None if isinstance(value, str) and not value.strip() else value


@lru_cache
def get_settings() -> Settings:
    return Settings()
