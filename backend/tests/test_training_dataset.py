"""The fine-tuning dataset: grounded, multilingual, correctly formatted, deterministic split."""

import asyncio
import json
from pathlib import Path
from typing import Any

from app.services.llm_engine import ungrounded_numbers
from app.services.llm_tools import ToolExecutor, ToolOutcome
from app.training.dataset import build
from tests.test_history import _loaded_service


def test_dataset_is_grounded_and_well_formed(tmp_path: Path, container: Any) -> None:
    history = asyncio.run(_loaded_service(tmp_path))
    executor = ToolExecutor(container.sports, container.predictions, container.forex)
    executor.history = history
    out = tmp_path / "training"
    summary = asyncio.run(build(history, executor, out, min_meetings=1, per_pair=3, recent_seasons=2, per_team=4, guardrails=6))

    assert summary["rejected_ungrounded"] == 0
    assert summary["train"] + summary["eval"] > 20
    assert {"head_to_head", "team_stats", "finish", "guardrail"} <= set(summary["by_kind"])
    assert set(summary["by_language"]) == {"en", "sw", "sheng"}

    rows = [json.loads(line) for line in (out / "train.jsonl").read_text(encoding="utf-8").splitlines()]
    tool_names = {t["function"]["name"] for t in rows[0]["tools"]}
    assert {"get_head_to_head_history", "get_team_history_stats", "get_league_table_history"} <= tool_names
    for row in rows:
        roles = [m["role"] for m in row["messages"]]
        assert roles[0] == "system" and roles[1] == "user" and roles[-1] == "assistant"
        if "tool" in roles:  # tool conversations: call -> real result -> answer grounded in that result
            call, result, answer = row["messages"][2], row["messages"][3], row["messages"][4]
            assert call["tool_calls"][0]["function"]["name"] == result["name"]
            assert isinstance(call["tool_calls"][0]["function"]["arguments"], dict)
            assert ungrounded_numbers(answer["content"], [ToolOutcome(content=result["content"])]) == []

    # Re-running gives the same evaluation set (deterministic split).
    first_eval = (out / "eval.jsonl").read_text(encoding="utf-8")
    asyncio.run(build(history, executor, out, min_meetings=1, per_pair=3, recent_seasons=2, per_team=4, guardrails=6))
    assert (out / "eval.jsonl").read_text(encoding="utf-8") == first_eval
