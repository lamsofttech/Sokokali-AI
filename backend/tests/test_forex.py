import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.container import build_container
from app.integrations.forex.base import ForexDataError
from app.integrations.forex.simulated import SimulatedForexProvider
from app.main import create_app
from app.schemas.chat import Intent
from app.schemas.forex import Candle, SignalDirection
from app.services.ai_engine import SokokaliAI
from app.services.forex_engine import (
    ForexSignalEngine,
    PairNotFoundError,
    atr,
    ema_series,
    macd_histogram,
    rsi,
    trade_levels,
)


def _candles(closes: list[float], spread: float = 0.001) -> list[Candle]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        Candle(time=start + timedelta(hours=i), open=c, high=c + spread, low=c - spread, close=c)
        for i, c in enumerate(closes)
    ]


def _engine(provider: SimulatedForexProvider, levels: bool = False) -> ForexSignalEngine:
    return ForexSignalEngine(provider, model_version="fx-test", trade_levels_enabled=levels)


# --- indicators -------------------------------------------------------------


def test_ema_of_constant_series_is_constant() -> None:
    assert ema_series([1.5] * 30, 10) == pytest.approx([1.5] * 21)


def test_ema_rejects_short_input() -> None:
    with pytest.raises(ValueError):
        ema_series([1.0, 2.0], 5)


def test_rsi_extremes() -> None:
    assert rsi([float(i) for i in range(1, 40)]) == 100.0
    assert rsi([float(i) for i in range(40, 1, -1)]) == pytest.approx(0.0)
    assert rsi([1.0] * 40) == 50.0


def test_macd_histogram_zero_for_flat_prices() -> None:
    assert macd_histogram([1.1] * 80) == pytest.approx(0.0, abs=1e-12)


def test_atr_of_constant_range() -> None:
    assert atr(_candles([1.0] * 30, spread=0.002)) == pytest.approx(0.004)


def test_trade_levels_geometry() -> None:
    stop, target = trade_levels(SignalDirection.BUY, 1.1, 0.01)
    assert stop == pytest.approx(1.085) and target == pytest.approx(1.12)
    stop, target = trade_levels(SignalDirection.SELL, 1.1, 0.01)
    assert stop == pytest.approx(1.115) and target == pytest.approx(1.08)
    assert trade_levels(SignalDirection.NEUTRAL, 1.1, 0.01) is None


# --- provider and engine ----------------------------------------------------


def test_simulated_provider_is_deterministic_and_flagged() -> None:
    now = datetime(2026, 10, 24, 12, tzinfo=UTC)
    a = asyncio.run(SimulatedForexProvider(seed=1, now=now).get_candles("EURUSD"))
    b = asyncio.run(SimulatedForexProvider(seed=1, now=now).get_candles("EURUSD"))
    assert a == b
    assert SimulatedForexProvider.is_simulated is True
    assert all(c.low <= min(c.open, c.close) and c.high >= max(c.open, c.close) for c in a)
    assert a[-1].time < now


def test_simulated_provider_rejects_unknown_pair(forex_provider: SimulatedForexProvider) -> None:
    with pytest.raises(ForexDataError):
        asyncio.run(forex_provider.get_candles("XXXYYY"))


def test_signal_contract_without_trade_levels(forex_provider: SimulatedForexProvider) -> None:
    signal = asyncio.run(_engine(forex_provider).signal("eur/usd"))
    assert signal.symbol == "EURUSD"
    assert signal.trade_levels_enabled is False
    assert signal.entry is None and signal.stop_loss is None and signal.take_profit is None
    assert signal.freshness.is_simulated is True
    assert 0 <= signal.indicators.rsi <= 100
    assert any("SIMULATED" in f for f in signal.key_factors)
    assert "not financial advice" in signal.disclaimer


def test_signal_levels_when_enabled(forex_provider: SimulatedForexProvider) -> None:
    for signal in asyncio.run(_engine(forex_provider, levels=True).signals()):
        if signal.direction == SignalDirection.BUY:
            assert signal.stop_loss < signal.entry < signal.take_profit
        elif signal.direction == SignalDirection.SELL:
            assert signal.take_profit < signal.entry < signal.stop_loss
        else:
            assert signal.stop_loss is None


def test_unknown_pair_raises(forex_provider: SimulatedForexProvider) -> None:
    with pytest.raises(PairNotFoundError):
        asyncio.run(_engine(forex_provider).signal("ABCDEF"))


def test_find_pairs_by_alias(forex_provider: SimulatedForexProvider) -> None:
    pairs = asyncio.run(_engine(forex_provider).find_pairs("Pauni na EUR/USD, then usdkes and yen"))
    assert [p.symbol for p in pairs] == ["GBPUSD", "EURUSD", "USDKES", "USDJPY"]


def test_forex_intent_detection() -> None:
    ai = SokokaliAI()
    assert ai.classify_intent("forex signals today", 0) == Intent.FOREX
    assert ai.classify_intent("anything", 0, pair_count=1) == Intent.FOREX
    assert ai.classify_intent("guaranteed forex profit", 0) == Intent.GUARANTEE_REQUEST
    assert ai.classify_intent("Arsenal vs Chelsea", 2) == Intent.PREDICTION


# --- API --------------------------------------------------------------------


def test_forex_pairs_endpoint(client: TestClient) -> None:
    symbols = [p["symbol"] for p in client.get("/api/v1/forex/pairs").json()]
    assert "EURUSD" in symbols and "USDKES" in symbols


def test_forex_signals_endpoint(client: TestClient) -> None:
    body = client.get("/api/v1/forex/signals").json()
    assert len(body["signals"]) == 5
    assert all(s["trade_levels_enabled"] is False for s in body["signals"])


def test_forex_signal_endpoint(client: TestClient) -> None:
    body = client.get("/api/v1/forex/signals/USDKES").json()
    assert body["display_name"] == "USD/KES"
    assert body["direction"] in {"buy", "sell", "neutral"}
    assert client.get("/api/v1/forex/signals/eur-usd").status_code == 200
    assert client.get("/api/v1/forex/signals/ABCDEF").status_code == 404
    assert client.get("/api/v1/forex/signals/E1").status_code == 422


def test_forex_disabled(settings: Settings) -> None:
    disabled = settings.model_copy(update={"forex_enabled": False})
    with TestClient(create_app(disabled, build_container(disabled))) as client:
        assert client.get("/api/v1/forex/signals").status_code == 403
        body = client.post("/api/v1/chat", json={"message": "EUR/USD signal"}).json()
        assert body["intent"] == "forex"
        assert body["forex_signals"] == []
        assert "switched off" in body["reply"]


def test_status_reports_forex(client: TestClient) -> None:
    components = {c["name"]: c for c in client.get("/api/v1/status").json()["components"]}
    assert "SIMULATED" in components["forex_provider"]["detail"]
    assert "disabled pending licensing review" in components["forex_signal_engine"]["detail"]


# --- chat -------------------------------------------------------------------


def test_chat_single_pair_english(client: TestClient) -> None:
    body = client.post("/api/v1/chat", json={"message": "EUR/USD signal please"}).json()
    assert body["intent"] == "forex"
    assert body["language"] == "en"
    assert body["currency_pairs"] == ["EUR/USD"]
    assert len(body["forex_signals"]) == 1
    assert "not financial advice" in body["reply"]
    assert "Stop-loss" not in body["reply"]  # trade levels disabled by default
    assert body["is_simulated_data"] is True
    assert "Simulated" in body["reply"]


def test_chat_overview_swahili(client: TestClient) -> None:
    body = client.post("/api/v1/chat", json={"message": "Nipe uchambuzi wa forex leo"}).json()
    assert body["intent"] == "forex"
    assert body["language"] == "sw"
    assert len(body["forex_signals"]) == 5
    assert "si ushauri wa kifedha" in body["reply"]


def test_chat_sheng_pair(client: TestClient) -> None:
    body = client.post("/api/v1/chat", json={"message": "Niaje msee, usdkes iko aje?"}).json()
    assert body["language"] == "sheng"
    assert body["currency_pairs"] == ["USD/KES"]
    assert "financial advice" in body["reply"]


def test_chat_levels_when_enabled(settings: Settings, forex_provider: SimulatedForexProvider) -> None:
    licensed = settings.model_copy(update={"forex_trade_levels_enabled": True})
    with TestClient(create_app(licensed, build_container(licensed, forex_provider=forex_provider))) as client:
        signals = client.get("/api/v1/forex/signals").json()["signals"]
        directional = next((s for s in signals if s["direction"] != "neutral"), None)
        assert directional is not None, "simulated data should contain at least one directional signal"
        body = client.post("/api/v1/chat", json={"message": f"{directional['symbol']} signal"}).json()
    assert "Stop-loss" in body["reply"]


def test_chat_guaranteed_forex_profit(client: TestClient) -> None:
    body = client.post("/api/v1/chat", json={"message": "Give me guaranteed forex profit"}).json()
    assert body["intent"] == "guarantee_request"
    assert "red flag" in body["reply"]
    assert body["forex_signals"] == []
