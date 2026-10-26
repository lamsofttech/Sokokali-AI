"""Forex market data and signal contracts."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.schemas.common import DataFreshness


class CurrencyPair(BaseModel):
    symbol: str = Field(description="Six-letter code, e.g. EURUSD")
    display_name: str = Field(description="e.g. EUR/USD")
    decimals: int = Field(ge=0, le=8)
    aliases: list[str] = Field(default_factory=list, description="Lower-case names viewers may use")


class Candle(BaseModel):
    time: datetime
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)


class SignalDirection(StrEnum):
    BUY = "buy"
    SELL = "sell"
    NEUTRAL = "neutral"


class SignalStrength(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Indicators(BaseModel):
    ema_fast: float
    ema_slow: float
    rsi: float = Field(ge=0, le=100)
    macd_histogram: float
    atr: float = Field(ge=0)


class ForexSignal(BaseModel):
    symbol: str
    display_name: str
    timeframe: str
    generated_at: datetime
    freshness: DataFreshness
    direction: SignalDirection
    strength: SignalStrength = Field(description="Indicator agreement, NOT a calibrated win probability")
    price: float
    trade_levels_enabled: bool = Field(
        description="False until a licensing review allows publishing entry/stop/target levels"
    )
    entry: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    risk_reward: float | None = None
    indicators: Indicators
    key_factors: list[str]
    model_version: str
    disclaimer: str = (
        "Educational technical analysis only, not financial advice. Forex trading is high-risk and you can "
        "lose all of your money. Past patterns do not guarantee future results."
    )


class ForexSignalList(BaseModel):
    signals: list[ForexSignal]
