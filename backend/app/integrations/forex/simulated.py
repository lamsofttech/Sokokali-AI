"""Deterministic simulated forex prices for local development.

Prices start near realistic levels but every candle is SYNTHETIC (a seeded
random walk with changing trend regimes). Never use them for real trading.
"""

import math
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.integrations.forex.base import ForexDataError, ForexDataProvider
from app.schemas.forex import Candle, CurrencyPair


@dataclass(frozen=True)
class _SimPair:
    symbol: str
    display_name: str
    decimals: int
    aliases: tuple[str, ...]
    start_price: float
    hourly_volatility: float  # standard deviation of hourly log returns


_PAIRS = [
    _SimPair("EURUSD", "EUR/USD", 5, ("eurusd", "eur/usd", "eur usd", "euro", "fiber"), 1.08, 0.0012),
    _SimPair("GBPUSD", "GBP/USD", 5, ("gbpusd", "gbp/usd", "gbp usd", "pound", "pauni", "cable"), 1.27, 0.0013),
    _SimPair("USDJPY", "USD/JPY", 3, ("usdjpy", "usd/jpy", "usd jpy", "yen"), 150.0, 0.0013),
    _SimPair("AUDUSD", "AUD/USD", 5, ("audusd", "aud/usd", "aud usd", "aussie"), 0.66, 0.0014),
    _SimPair(
        "USDKES", "USD/KES", 3, ("usdkes", "usd/kes", "usd kes", "shilling", "shilingi", "kes"), 129.0, 0.0004
    ),
]

_HISTORY_HOURS = 500
_REGIME_HOURS = 60  # the simulated trend changes direction every ~2.5 days


class SimulatedForexProvider(ForexDataProvider):
    name = "simulated"
    is_simulated = True

    def __init__(self, seed: int = 2024, now: datetime | None = None) -> None:
        self._now = (now or datetime.now(UTC)).replace(minute=0, second=0, microsecond=0)
        self._pairs = {p.symbol: p for p in _PAIRS}
        self._candles = {p.symbol: self._generate(p, random.Random(f"{seed}-{p.symbol}")) for p in _PAIRS}

    def _generate(self, pair: _SimPair, rng: random.Random) -> list[Candle]:
        candles: list[Candle] = []
        price = pair.start_price
        drift = 0.0
        start = self._now - timedelta(hours=_HISTORY_HOURS)
        for hour in range(_HISTORY_HOURS):
            if hour % _REGIME_HOURS == 0:
                drift = rng.uniform(-0.35, 0.35) * pair.hourly_volatility
            open_ = price
            close = open_ * math.exp(drift + rng.gauss(0, pair.hourly_volatility))
            wick = pair.hourly_volatility / 2
            high = max(open_, close) * (1 + abs(rng.gauss(0, wick)))
            low = min(open_, close) * (1 - abs(rng.gauss(0, wick)))
            candles.append(
                Candle(
                    time=start + timedelta(hours=hour),
                    open=round(open_, pair.decimals),
                    high=round(high, pair.decimals),
                    low=round(low, pair.decimals),
                    close=round(close, pair.decimals),
                )
            )
            price = close
        return candles

    async def list_pairs(self) -> list[CurrencyPair]:
        return [
            CurrencyPair(symbol=p.symbol, display_name=p.display_name, decimals=p.decimals, aliases=list(p.aliases))
            for p in self._pairs.values()
        ]

    async def get_candles(self, symbol: str, timeframe: str = "H1", limit: int = 300) -> list[Candle]:
        if timeframe != "H1":
            raise ForexDataError(f"Simulated provider only supports H1 candles, not {timeframe}")
        candles = self._candles.get(symbol.upper())
        if candles is None:
            raise ForexDataError(f"Unknown currency pair {symbol}")
        return candles[-limit:]

    def data_as_of(self) -> datetime:
        return self._now
