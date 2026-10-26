"""Forex technical-analysis signals.

Model (version set by ``Settings.forex_signal_model_version``) scores three
indicators on hourly candles, each voting +1 (bullish), -1 (bearish) or 0:

1. Trend: EMA(20) above or below EMA(50).
2. Momentum: sign of the MACD(12, 26, 9) histogram.
3. Mean reversion: RSI(14) below 30 votes bullish, above 70 bearish.

A total of +2 or more is BUY, -2 or less is SELL, anything else NEUTRAL.
``strength`` says how many indicators agree; it is not a win probability.
Stop-loss and take-profit are 1.5x and 2x ATR(14) from the last close.

Compliance boundary: publishing entry/stop/target levels to the public may
count as regulated investment advice, so levels are only included when
``Settings.forex_trade_levels_enabled`` is true (default false). The signal
has not been backtested yet (planned with the Phase 3 evaluation work).
"""

import re
from datetime import UTC, datetime

from app.integrations.forex.base import ForexDataProvider
from app.schemas.forex import (
    Candle,
    CurrencyPair,
    ForexSignal,
    Indicators,
    SignalDirection,
    SignalStrength,
)

EMA_FAST, EMA_SLOW = 20, 50
RSI_PERIOD, ATR_PERIOD = 14, 14
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
STOP_ATR, TARGET_ATR = 1.5, 2.0
MIN_CANDLES = EMA_SLOW + MACD_SIGNAL


class InsufficientForexDataError(Exception):
    pass


class PairNotFoundError(Exception):
    pass


def ema_series(values: list[float], period: int) -> list[float]:
    """EMA seeded with a simple average; element ``i`` corresponds to ``values[i + period - 1]``."""
    if period < 1 or len(values) < period:
        raise ValueError("Need at least `period` values")
    k = 2 / (period + 1)
    out = [sum(values[:period]) / period]
    for value in values[period:]:
        out.append(value * k + out[-1] * (1 - k))
    return out


def rsi(closes: list[float], period: int = RSI_PERIOD) -> float:
    """Wilder's RSI of the latest close."""
    if len(closes) <= period:
        raise ValueError("Need more than `period` closes")
    changes = [b - a for a, b in zip(closes, closes[1:], strict=False)]
    avg_gain = sum(max(c, 0) for c in changes[:period]) / period
    avg_loss = sum(max(-c, 0) for c in changes[:period]) / period
    for c in changes[period:]:
        avg_gain = (avg_gain * (period - 1) + max(c, 0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-c, 0)) / period
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    return 100 - 100 / (1 + avg_gain / avg_loss)


def macd_histogram(closes: list[float]) -> float:
    fast = ema_series(closes, MACD_FAST)
    slow = ema_series(closes, MACD_SLOW)
    macd_line = [f - s for f, s in zip(fast[-len(slow) :], slow, strict=True)]
    return macd_line[-1] - ema_series(macd_line, MACD_SIGNAL)[-1]


def atr(candles: list[Candle], period: int = ATR_PERIOD) -> float:
    """Wilder's Average True Range of the latest candle."""
    if len(candles) <= period:
        raise ValueError("Need more than `period` candles")
    ranges = [
        max(c.high - c.low, abs(c.high - prev.close), abs(c.low - prev.close))
        for prev, c in zip(candles, candles[1:], strict=False)
    ]
    value = sum(ranges[:period]) / period
    for r in ranges[period:]:
        value = (value * (period - 1) + r) / period
    return value


def trade_levels(direction: SignalDirection, price: float, atr_value: float) -> tuple[float, float] | None:
    """(stop_loss, take_profit) for a directional signal, ``None`` when neutral."""
    if direction == SignalDirection.BUY:
        return price - STOP_ATR * atr_value, price + TARGET_ATR * atr_value
    if direction == SignalDirection.SELL:
        return price + STOP_ATR * atr_value, price - TARGET_ATR * atr_value
    return None


class ForexSignalEngine:
    def __init__(
        self,
        provider: ForexDataProvider,
        model_version: str,
        trade_levels_enabled: bool = False,
        timeframe: str = "H1",
    ) -> None:
        self.provider = provider
        self.model_version = model_version
        self.trade_levels_enabled = trade_levels_enabled
        self.timeframe = timeframe
        self._alias_pattern: re.Pattern[str] | None = None
        self._alias_to_pair: dict[str, CurrencyPair] = {}

    async def _pair(self, symbol: str) -> CurrencyPair:
        normalized = symbol.upper().replace("/", "").replace("-", "")
        for pair in await self.provider.list_pairs():
            if pair.symbol == normalized:
                return pair
        raise PairNotFoundError(symbol)

    async def find_pairs(self, text: str) -> list[CurrencyPair]:
        """Currency pairs mentioned in ``text``, in order of first appearance."""
        if self._alias_pattern is None:
            for pair in await self.provider.list_pairs():
                for alias in pair.aliases:
                    self._alias_to_pair[alias] = pair
            aliases = sorted(self._alias_to_pair, key=len, reverse=True)
            self._alias_pattern = re.compile(r"(?<!\w)(" + "|".join(re.escape(a) for a in aliases) + r")(?!\w)")
        found: list[CurrencyPair] = []
        for match in self._alias_pattern.finditer(text.lower()):
            pair = self._alias_to_pair[match.group(1)]
            if all(p.symbol != pair.symbol for p in found):
                found.append(pair)
        return found

    async def signals(self) -> list[ForexSignal]:
        return [await self.signal(p.symbol) for p in await self.provider.list_pairs()]

    async def signal(self, symbol: str) -> ForexSignal:
        pair = await self._pair(symbol)
        candles = await self.provider.get_candles(pair.symbol, self.timeframe, limit=300)
        if len(candles) < MIN_CANDLES:
            raise InsufficientForexDataError(f"Only {len(candles)} candles for {pair.display_name}")

        closes = [c.close for c in candles]
        price = closes[-1]
        ema_fast = ema_series(closes, EMA_FAST)[-1]
        ema_slow = ema_series(closes, EMA_SLOW)[-1]
        rsi_value = rsi(closes)
        histogram = macd_histogram(closes)
        atr_value = atr(candles)

        trend_vote = 1 if ema_fast > ema_slow else -1
        momentum_vote = 1 if histogram > 0 else -1
        rsi_vote = 1 if rsi_value < 30 else -1 if rsi_value > 70 else 0
        score = trend_vote + momentum_vote + rsi_vote
        direction = (
            SignalDirection.BUY if score >= 2 else SignalDirection.SELL if score <= -2 else SignalDirection.NEUTRAL
        )
        strength = SignalStrength.HIGH if abs(score) == 3 else SignalStrength.MEDIUM if abs(score) == 2 else SignalStrength.LOW

        d = pair.decimals
        key_factors = [
            f"EMA{EMA_FAST} {ema_fast:.{d}f} is {'above' if trend_vote > 0 else 'below'} "
            f"EMA{EMA_SLOW} {ema_slow:.{d}f} ({'uptrend' if trend_vote > 0 else 'downtrend'})",
            f"MACD histogram {histogram:+.{d + 1}f} ({'bullish' if momentum_vote > 0 else 'bearish'} momentum)",
            f"RSI({RSI_PERIOD}) {rsi_value:.1f} "
            f"({'oversold' if rsi_vote > 0 else 'overbought' if rsi_vote < 0 else 'neutral zone'})",
            f"ATR({ATR_PERIOD}) {atr_value:.{d}f} (typical hourly range)",
        ]
        if self.provider.is_simulated:
            key_factors.append("All prices are SIMULATED, not real market data")

        entry = stop_loss = take_profit = risk_reward = None
        levels = trade_levels(direction, price, atr_value) if self.trade_levels_enabled else None
        if levels is not None:
            entry = price
            stop_loss, take_profit = round(levels[0], d), round(levels[1], d)
            risk_reward = round(TARGET_ATR / STOP_ATR, 2)

        return ForexSignal(
            symbol=pair.symbol,
            display_name=pair.display_name,
            timeframe=self.timeframe,
            generated_at=datetime.now(UTC),
            freshness=self.provider.freshness(),
            direction=direction,
            strength=strength,
            price=price,
            trade_levels_enabled=self.trade_levels_enabled,
            entry=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_reward=risk_reward,
            indicators=Indicators(
                ema_fast=round(ema_fast, d),
                ema_slow=round(ema_slow, d),
                rsi=round(rsi_value, 2),
                macd_histogram=histogram,
                atr=round(atr_value, d + 1),
            ),
            key_factors=key_factors,
            model_version=self.model_version,
        )
