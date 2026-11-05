import json
from unittest.mock import MagicMock

import anthropic

from environment import ENERGY_DRAIN
from llm_agent import Condition
from run_experiment import ROSTER, existing_run_files, run_one, run_paths


def pass_client() -> MagicMock:
    """Mock Anthropic client whose agents always choose pass."""
    block = MagicMock()
    block.type = "tool_use"
    block.input = {"action": "pass", "reasoning": "test"}
    message = MagicMock()
    message.content = [block]
    client = MagicMock(spec=anthropic.Anthropic)
    client.messages = MagicMock()
    client.messages.create.return_value = message
    return client


def test_run_one_writes_ticks_reasoning_and_meta(tmp_path):
    run_one(Condition.A, seed=7, log_dir=tmp_path, client=pass_client())
    paths = run_paths(tmp_path, Condition.A, 7)
    for p in paths.values():
        assert p.exists(), p

    ticks = [json.loads(line) for line in paths["ticks"].read_text().splitlines()]
    reasoning = [json.loads(line) for line in paths["reasoning"].read_text().splitlines()]
    assert ticks and reasoning
    assert {r["seed"] for r in reasoning} == {7}


def test_meta_records_config_prompts_and_code(tmp_path):
    run_one(Condition.C, seed=3, log_dir=tmp_path, client=pass_client())
    meta = json.loads(run_paths(tmp_path, Condition.C, 3)["meta"].read_text())

    assert meta["completed"] is True
    assert meta["condition"] == "C" and meta["seed"] == 3
    assert meta["constants"]["energy_drain"] == ENERGY_DRAIN
    assert set(meta["archetypes"]) == set(ROSTER)
    assert all(meta["archetypes"].values())
    for aid in ROSTER:
        prompt = meta["system_prompts"][aid]
        assert len(prompt["sha256"]) == 64
        assert f"loses {ENERGY_DRAIN} energy" in prompt["text"]
    assert {"environment.py", "llm_agent.py"} <= set(meta["code_sha256"])
    assert meta["ticks"] > 0


def test_reasoning_logs_are_per_seed_and_do_not_clobber(tmp_path):
    client = pass_client()
    run_one(Condition.A, seed=1, log_dir=tmp_path, client=client)
    first = run_paths(tmp_path, Condition.A, 1)["reasoning"].read_text()
    run_one(Condition.A, seed=2, log_dir=tmp_path, client=client)
    assert run_paths(tmp_path, Condition.A, 1)["reasoning"].read_text() == first


def test_existing_run_files_detects_clashes(tmp_path):
    assert existing_run_files(tmp_path, [Condition.A], [1, 2]) == []
    run_one(Condition.A, seed=2, log_dir=tmp_path, client=pass_client())
    clashes = existing_run_files(tmp_path, [Condition.A, Condition.B], [1, 2])
    assert set(clashes) == set(run_paths(tmp_path, Condition.A, 2).values())
