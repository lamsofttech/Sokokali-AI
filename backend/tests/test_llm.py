"""Claude integration tests against a scripted fake client (no network, no API cost)."""

import asyncio
import copy
import json
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.container import Container, build_container, build_llm_client
from app.integrations.forex.simulated import SimulatedForexProvider
from app.integrations.sports.simulated import SimulatedSportsProvider
from app.main import create_app
from app.services.llm_engine import FALLBACK_BETA, SYSTEM_PROMPT, ungrounded_numbers
from app.services.llm_tools import ToolOutcome


def text(value: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=value)


def tool_use(tool_id: str, name: str, tool_input: dict[str, str]) -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", id=tool_id, name=name, input=tool_input)


def response(stop_reason: str, *blocks: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(stop_reason=stop_reason, content=list(blocks), model="claude-opus-5-5")


class FakeMessages:
    def __init__(self, script: list[Any]) -> None:
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(copy.deepcopy(kwargs))
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeAnthropic:
    def __init__(self, script: list[Any]) -> None:
        self.messages = FakeMessages(script)
        self.beta = SimpleNamespace(messages=self.messages)
        self.closed = False

    async def close(self) -> None:
        self.closed = True


def _client_with(
    settings: Settings,
    provider: SimulatedSportsProvider,
    forex_provider: SimulatedForexProvider,
    script: list[Any],
) -> tuple[TestClient, FakeAnthropic, Container]:
    fake = FakeAnthropic(script)
    container = build_container(settings, sports_provider=provider, forex_provider=forex_provider, llm_client=fake)
    return TestClient(create_app(settings, container)), fake, container


def _chat(client: TestClient, message: str, viewer_id: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"message": message}
    if viewer_id:
        payload["viewer_id"] = viewer_id
    res = client.post("/api/v1/chat", json=payload)
    assert res.status_code == 200, res.text
    return res.json()


@pytest.fixture
def arsenal_chelsea_pcts(container: Container) -> tuple[int, int, int]:
    fixture = asyncio.run(container.sports_provider.get_fixtures())[0]
    p = asyncio.run(container.predictions.predict_fixture(fixture)).probabilities
    return round(p.home_win * 100), round(p.draw * 100), round(p.away_win * 100)


def test_llm_reply_with_prediction_tool(settings, provider, forex_provider, arsenal_chelsea_pcts) -> None:
    hp, dp, ap = arsenal_chelsea_pcts
    script = [
        response("tool_use", tool_use("t1", "get_match_prediction", {"team_a": "Arsenal", "team_b": "Chelsea"})),
        response("end_turn", text(f"Wadau! Arsenal {hp}%, sare {dp}%, Chelsea {ap}%. Mechi kali!")),
    ]
    client, fake, _ = _client_with(settings, provider, forex_provider, script)
    with client:
        body = _chat(client, "Sokokali, Arsenal na Chelsea nani atashinda?")

    assert body["engine"] == "llm"
    assert body["intent"] == "prediction"
    assert body["language"] == "sw"
    assert body["prediction"]["home_team"] == "Arsenal"
    assert body["reply"].startswith(f"Wadau! Arsenal {hp}%")
    assert "si uhakika" in body["reply"]  # deterministic disclaimer appended
    assert "majaribio" in body["reply"]  # simulated-data notice appended
    assert body["is_simulated_data"] is True

    first, second = fake.messages.calls
    assert first["model"] == "claude-opus-5-5"
    assert first["system"] == SYSTEM_PROMPT
    assert first["fallbacks"] == "default" and first["betas"] == [FALLBACK_BETA]
    assert first["output_config"] == {"effort": "low"}
    assert all(t["strict"] and t["input_schema"]["additionalProperties"] is False for t in first["tools"])
    assert "Kiswahili" in first["messages"][-1]["content"][0]["text"]
    tool_result = second["messages"][-1]["content"][0]
    assert tool_result["tool_use_id"] == "t1" and tool_result["is_error"] is False
    assert json.loads(tool_result["content"])["home_win_pct"] == hp
    # append-only: the second request starts with exactly the first request's messages
    assert second["messages"][: len(first["messages"])] == first["messages"]
    assert second["tools"] == first["tools"] and second["system"] == first["system"]


def test_llm_ungrounded_numbers_fall_back_to_rules(settings, provider, forex_provider) -> None:
    script = [response("end_turn", text("Arsenal have a 90% chance to win!"))]
    client, _, _ = _client_with(settings, provider, forex_provider, script)
    with client:
        body = _chat(client, "Arsenal vs Chelsea who will win?")
    assert body["engine"] == "rules"
    assert "90%" not in body["reply"]
    assert body["prediction"] is not None  # rule-based engine answered from verified data


def test_llm_outage_falls_back_and_cools_down(settings, provider, forex_provider) -> None:
    error = anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))
    client, fake, _ = _client_with(settings, provider, forex_provider, [error])
    with client:
        first = _chat(client, "Hello Sokokali")
        second = _chat(client, "fixtures")
        status = {c["name"]: c for c in client.get("/api/v1/status").json()["components"]}
    assert first["engine"] == "rules" and second["engine"] == "rules"
    assert len(fake.messages.calls) == 1  # no retry storm while cooling down
    assert status["ai_engine"]["status"] == "degraded"


def test_llm_refusal_falls_back(settings, provider, forex_provider) -> None:
    client, _, _ = _client_with(settings, provider, forex_provider, [response("refusal")])
    with client:
        assert _chat(client, "Hello")["engine"] == "rules"


def test_too_many_tool_rounds_falls_back(settings, provider, forex_provider) -> None:
    loop = [response("tool_use", tool_use(f"t{i}", "get_upcoming_fixtures", {"team": ""})) for i in range(10)]
    client, fake, container = _client_with(settings, provider, forex_provider, loop)
    with client:
        body = _chat(client, "fixtures please")
    assert body["engine"] == "rules"
    assert len(fake.messages.calls) == container.settings.llm_max_tool_rounds


def test_moderated_and_guarantee_messages_never_reach_llm(settings, provider, forex_provider) -> None:
    client, fake, _ = _client_with(settings, provider, forex_provider, [])
    with client:
        assert _chat(client, "Call me on 0712345678")["moderated"] is True
        assert _chat(client, "Nipe sure bet ya leo")["intent"] == "guarantee_request"
        assert _chat(client, "guaranteed forex profit")["intent"] == "guarantee_request"
    assert fake.messages.calls == []


def test_history_is_sent_as_text_for_same_viewer(settings, provider, forex_provider) -> None:
    script = [response("end_turn", text("Karibu sana!")), response("end_turn", text("Poa sana!"))]
    client, fake, _ = _client_with(settings, provider, forex_provider, script)
    with client:
        _chat(client, "Habari", viewer_id="fan-1")
        _chat(client, "Asante", viewer_id="fan-1")
    second = fake.messages.calls[1]["messages"]
    assert second[0]["role"] == "user" and "Habari" in second[0]["content"]
    assert second[1] == {"role": "assistant", "content": "Karibu sana!"}


def test_anonymous_viewers_do_not_share_history(settings, provider, forex_provider) -> None:
    script = [response("end_turn", text("Karibu!")), response("end_turn", text("Karibu tena!"))]
    client, fake, _ = _client_with(settings, provider, forex_provider, script)
    with client:
        _chat(client, "Habari")
        _chat(client, "Mambo")
    assert len(fake.messages.calls[1]["messages"]) == 1


def test_forex_tool_reply_gets_risk_warning(settings, provider, forex_provider) -> None:
    script = [
        response("tool_use", tool_use("f1", "get_forex_signal", {"pair": "EUR/USD"})),
        response("end_turn", text("EUR/USD is looking bearish on the hourly chart.")),
    ]
    client, fake, _ = _client_with(settings, provider, forex_provider, script)
    with client:
        body = _chat(client, "What about the euro?")
    assert body["engine"] == "llm" and body["intent"] == "forex"
    assert body["currency_pairs"] == ["EUR/USD"]
    assert "not financial advice" in body["reply"]
    result = json.loads(fake.messages.calls[1]["messages"][-1]["content"][0]["content"])
    assert result["trade_levels_enabled"] is False
    assert all(s["stop_loss"] is None for s in result["signals"])


def test_unknown_team_tool_returns_error_result(settings, provider, forex_provider) -> None:
    script = [
        response("tool_use", tool_use("t1", "get_team_form", {"team": "Real Madrid"})),
        response("end_turn", text("Sorry, I don't have data on Real Madrid.")),
    ]
    client, fake, _ = _client_with(settings, provider, forex_provider, script)
    with client:
        body = _chat(client, "How is Real Madrid doing?")
    result = fake.messages.calls[1]["messages"][-1]["content"][0]
    assert result["is_error"] is True and "Unknown team" in result["content"]
    assert body["engine"] == "llm" and body["is_simulated_data"] is False


def test_client_closed_on_shutdown(settings, provider, forex_provider) -> None:
    client, fake, _ = _client_with(settings, provider, forex_provider, [])
    with client:
        pass
    assert fake.closed is True


def test_ungrounded_numbers() -> None:
    outcome = ToolOutcome(content=json.dumps({"home_win_pct": 33, "draw_pct": 26, "expected_goals_home": 1.29}))
    assert ungrounded_numbers("Arsenal 33%, draw 26%, xG 1.3", [outcome]) == []
    assert ungrounded_numbers("Arsenal 34% to win", [outcome]) == []  # ±1 point for rounding
    assert ungrounded_numbers("Arsenal 45% to win", [outcome]) == ["45%"]
    assert ungrounded_numbers("xG of 2.7", [outcome]) == ["2.7"]
    assert ungrounded_numbers("Kickoff 16:00 on 25/10", []) == []
    assert ungrounded_numbers("Arsenal 33%", [ToolOutcome(content='{"error": "x"}', is_error=True)]) == ["33%"]


def test_build_llm_client(settings: Settings) -> None:
    assert build_llm_client(settings) is None  # provider "none"
    auto = settings.model_copy(update={"llm_provider": "auto", "anthropic_api_key": None})
    assert build_llm_client(auto) is None
    from pydantic import SecretStr

    keyed = settings.model_copy(update={"llm_provider": "auto", "anthropic_api_key": SecretStr("sk-test")})
    assert isinstance(build_llm_client(keyed), anthropic.AsyncAnthropic)
