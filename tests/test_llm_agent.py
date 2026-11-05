import pytest
from pydantic import ValidationError
from unittest.mock import MagicMock, patch

from environment import BuyEnergyAction, PassAction, TransferAction, WorkAction
from llm_agent import (
    ARCHETYPES,
    ActionResponse,
    Condition,
    LLMAgent,
    build_system_prompt,
    build_user_prompt,
    response_to_action,
)
import anthropic


def base_obs(**kwargs):
    defaults = {
        "agent_id": "agent_0",
        "energy": 80,
        "coins": 5,
        "bank_rate": 10,
        "tick": 5,
        "ledger": [],
        "alive_agents": ["agent_0", "agent_1"],
    }
    return {**defaults, **kwargs}


def mock_tool_response(action: str, **kwargs) -> MagicMock:
    """Return a fake Anthropic API response containing one tool_use block."""
    tool_input = {"action": action, "reasoning": "test", **kwargs}
    block = MagicMock()
    block.type = "tool_use"
    block.input = tool_input
    message = MagicMock()
    message.content = [block]
    return message


def make_agent(condition=Condition.A, archetype=None, client=None) -> LLMAgent:
    mock_client = client or MagicMock(spec=anthropic.Anthropic)
    return LLMAgent("agent_0", condition, archetype=archetype, client=mock_client)


# ── build_system_prompt ───────────────────────────────────────────────────────

class TestBuildSystemPrompt:
    def test_condition_a_contains_rules(self):
        prompt = build_system_prompt(Condition.A)
        assert "Modulo Dilemma" in prompt
        assert "wrap" in prompt.lower()

    def test_condition_a_has_no_archetype_section(self):
        prompt = build_system_prompt(Condition.A)
        assert "CULTURAL BACKGROUND" not in prompt

    def test_condition_b_has_no_archetype_section(self):
        prompt = build_system_prompt(Condition.B)
        assert "CULTURAL BACKGROUND" not in prompt

    def test_condition_c_with_archetype_injects_backstory(self):
        prompt = build_system_prompt(Condition.C, archetype="circulationist")
        assert "CULTURAL BACKGROUND" in prompt
        assert "circulation is sacred" in prompt

    def test_condition_c_without_archetype_omits_section(self):
        prompt = build_system_prompt(Condition.C, archetype=None)
        assert "CULTURAL BACKGROUND" not in prompt

    def test_unknown_archetype_omits_section(self):
        prompt = build_system_prompt(Condition.C, archetype="unknown_archetype")
        assert "CULTURAL BACKGROUND" not in prompt

    def test_each_archetype_produces_distinct_prompts(self):
        prompts = [build_system_prompt(Condition.C, archetype=a) for a in ARCHETYPES]
        assert len(set(prompts)) == len(ARCHETYPES)


# ── build_user_prompt ─────────────────────────────────────────────────────────

class TestBuildUserPrompt:
    def test_contains_current_state(self):
        prompt = build_user_prompt(base_obs(energy=80, coins=5, bank_rate=10, tick=5), Condition.A)
        assert "energy=80" in prompt
        assert "coins=5" in prompt
        assert "BANK RATE: 10" in prompt
        assert "TICK: 5" in prompt

    def test_lists_alive_agents(self):
        prompt = build_user_prompt(base_obs(alive_agents=["a", "b"]), Condition.A)
        assert "a" in prompt and "b" in prompt

    def test_condition_a_has_no_memory_reflection(self):
        prompt = build_user_prompt(base_obs(), Condition.A)
        assert "review the public ledger" not in prompt

    def test_condition_b_has_memory_reflection(self):
        prompt = build_user_prompt(base_obs(), Condition.B)
        assert "review the public ledger" in prompt

    def test_condition_c_has_memory_reflection(self):
        prompt = build_user_prompt(base_obs(), Condition.C)
        assert "review the public ledger" in prompt

    def test_ledger_entries_rendered(self):
        ledger = [{"tick": 3, "event_type": "work", "agent_id": "agent_1"}]
        prompt = build_user_prompt(base_obs(ledger=ledger), Condition.A)
        assert "agent_1" in prompt

    def test_transfer_ledger_entry_includes_target_and_amount(self):
        ledger = [{"tick": 2, "event_type": "transfer", "agent_id": "agent_0",
                   "target_id": "agent_1", "amount": 3}]
        prompt = build_user_prompt(base_obs(ledger=ledger), Condition.A)
        assert "agent_1" in prompt
        assert "amount=3" in prompt

    def test_empty_ledger_shows_placeholder(self):
        prompt = build_user_prompt(base_obs(ledger=[]), Condition.A)
        assert "no entries yet" in prompt


# ── response_to_action ────────────────────────────────────────────────────────

class TestResponseToAction:
    def test_work_with_effort(self):
        resp = ActionResponse(action="work", reasoning="r", effort="high")
        action = response_to_action(resp)
        assert isinstance(action, WorkAction)
        assert action.effort == "high"

    def test_buy_energy(self):
        resp = ActionResponse(action="buy_energy", reasoning="r", coins_to_spend=3)
        action = response_to_action(resp)
        assert isinstance(action, BuyEnergyAction)
        assert action.coins_to_spend == 3

    def test_transfer_valid_target(self):
        resp = ActionResponse(action="transfer", reasoning="r", target_id="agent_1", amount=2)
        action = response_to_action(resp)
        assert isinstance(action, TransferAction)
        assert action.target_id == "agent_1"
        assert action.amount == 2

    def test_self_transfer_passed_through_unchanged(self):
        # No silent redirect: the environment must see (and reject) what the agent chose.
        resp = ActionResponse(action="transfer", reasoning="r", target_id="agent_0", amount=1)
        action = response_to_action(resp)
        assert isinstance(action, TransferAction)
        assert action.target_id == "agent_0"

    def test_invalid_target_passed_through_unchanged(self):
        resp = ActionResponse(action="transfer", reasoning="r", target_id="ghost", amount=1)
        action = response_to_action(resp)
        assert isinstance(action, TransferAction)
        assert action.target_id == "ghost"

    def test_pass_action(self):
        resp = ActionResponse(action="pass", reasoning="r")
        assert isinstance(response_to_action(resp), PassAction)


class TestActionResponseRequiredFields:
    @pytest.mark.parametrize("action, fields", [
        ("work", {}),
        ("buy_energy", {}),
        ("transfer", {"amount": 1}),
        ("transfer", {"target_id": "agent_1"}),
    ])
    def test_missing_required_field_is_a_validation_error(self, action, fields):
        with pytest.raises(ValidationError):
            ActionResponse(action=action, reasoning="r", **fields)

    def test_pass_needs_no_extra_fields(self):
        ActionResponse(action="pass", reasoning="r")


# ── LLMAgent.decide ───────────────────────────────────────────────────────────

class TestLLMAgentDecide:
    def _agent(self, condition=Condition.A):
        mock_client = MagicMock(spec=anthropic.Anthropic)
        mock_client.messages = MagicMock()
        agent = LLMAgent("agent_0", condition, client=mock_client)
        return agent, mock_client

    def test_returns_work_action(self):
        agent, client = self._agent()
        client.messages.create.return_value = mock_tool_response("work", effort="medium")
        action = agent.decide("agent_0", base_obs())
        assert isinstance(action, WorkAction)

    def test_returns_buy_energy_action(self):
        agent, client = self._agent()
        client.messages.create.return_value = mock_tool_response("buy_energy", coins_to_spend=2)
        action = agent.decide("agent_0", base_obs())
        assert isinstance(action, BuyEnergyAction)

    def test_returns_transfer_action(self):
        agent, client = self._agent()
        client.messages.create.return_value = mock_tool_response(
            "transfer", target_id="agent_1", amount=1
        )
        action = agent.decide("agent_0", base_obs())
        assert isinstance(action, TransferAction)

    def test_returns_pass_action(self):
        agent, client = self._agent()
        client.messages.create.return_value = mock_tool_response("pass")
        action = agent.decide("agent_0", base_obs())
        assert isinstance(action, PassAction)

    def test_reasoning_logged(self):
        agent, client = self._agent()
        client.messages.create.return_value = mock_tool_response("pass")
        agent.decide("agent_0", base_obs(tick=7))
        assert len(agent.reasoning_log) == 1
        assert agent.reasoning_log[0]["tick"] == 7

    def test_api_error_falls_back_to_pass(self):
        agent, client = self._agent()
        client.messages.create.side_effect = anthropic.APIStatusError(
            "rate limit", response=MagicMock(status_code=429), body={}
        )
        action = agent.decide("agent_0", base_obs())
        assert isinstance(action, PassAction)
        assert agent.failures == 1

    def test_missing_tool_block_falls_back_to_pass(self):
        agent, client = self._agent()
        message = MagicMock()
        message.content = []  # no tool_use block
        client.messages.create.return_value = message
        action = agent.decide("agent_0", base_obs())
        assert isinstance(action, PassAction)
        assert agent.failures == 1

    def test_schema_validation_error_falls_back_to_pass(self):
        agent, client = self._agent()
        block = MagicMock()
        block.type = "tool_use"
        block.input = {"action": "invalid_action", "reasoning": "r"}  # invalid enum
        message = MagicMock()
        message.content = [block]
        client.messages.create.return_value = message
        action = agent.decide("agent_0", base_obs())
        assert isinstance(action, PassAction)
        assert agent.failures == 1

    def test_failure_logged_in_reasoning_log(self):
        agent, client = self._agent()
        client.messages.create.side_effect = Exception("unexpected")
        agent.decide("agent_0", base_obs(tick=3))
        assert len(agent.reasoning_log) == 1
        assert "error" in agent.reasoning_log[0]

    def test_uses_condition_b_system_prompt(self):
        agent, client = self._agent(Condition.B)
        client.messages.create.return_value = mock_tool_response("pass")
        agent.decide("agent_0", base_obs())
        call_kwargs = client.messages.create.call_args
        user_msg = call_kwargs[1]["messages"][0]["content"]
        assert "review the public ledger" in user_msg

    def test_condition_c_with_archetype_injects_backstory(self):
        mock_client = MagicMock(spec=anthropic.Anthropic)
        mock_client.messages = MagicMock()
        mock_client.messages.create.return_value = mock_tool_response("pass")
        agent = LLMAgent(
            "agent_0", Condition.C, archetype="accelerationist", client=mock_client
        )
        agent.decide("agent_0", base_obs())
        system = mock_client.messages.create.call_args[1]["system"]
        assert "dissident" in system


# ── Unbounded (capitalism baseline) prompt ────────────────────────────────────

class TestUnboundedPrompt:
    def test_unbounded_prompt_has_no_wraparound_language(self):
        prompt = build_system_prompt(Condition.A, unbounded=True)
        assert "wrap" not in prompt.lower()
        assert "modulo" not in prompt.lower()
        assert "0 and 19" not in prompt

    def test_unbounded_prompt_says_balance_grows_without_limit(self):
        prompt = build_system_prompt(Condition.A, unbounded=True)
        assert "without limit" in prompt

    def test_unbounded_condition_c_ignores_archetype(self):
        prompt = build_system_prompt(Condition.C, archetype="circulationist", unbounded=True)
        assert "CULTURAL BACKGROUND" not in prompt
        assert "circulation" not in prompt.lower()

    def test_unbounded_agent_uses_unbounded_prompt(self):
        mock_client = MagicMock(spec=anthropic.Anthropic)
        mock_client.messages = MagicMock()
        mock_client.messages.create.return_value = mock_tool_response("pass")
        agent = LLMAgent("agent_0", Condition.A, client=mock_client, unbounded=True)
        agent.decide("agent_0", base_obs())
        system = mock_client.messages.create.call_args[1]["system"]
        assert "without limit" in system
        assert "wrap" not in system.lower()


# ── Condition D (transparent balances) ───────────────────────────────────────

class TestConditionD:
    def test_system_prompt_includes_transparency_note(self):
        prompt = build_system_prompt(Condition.D)
        assert "public" in prompt.lower()
        assert "all agents" in prompt.lower()

    def test_user_prompt_includes_other_agents_state_when_present(self):
        obs = base_obs(all_agents_state={"agent_1": {"coins": 12, "energy": 45}})
        prompt = build_user_prompt(obs, Condition.D)
        assert "agent_1" in prompt
        assert "coins=12" in prompt
        assert "energy=45" in prompt

    def test_user_prompt_omits_section_when_no_all_agents_state(self):
        obs = base_obs()  # no all_agents_state key
        prompt = build_user_prompt(obs, Condition.D)
        assert "ALL AGENTS" not in prompt

    def test_condition_a_user_prompt_ignores_all_agents_state(self):
        obs = base_obs(all_agents_state={"agent_1": {"coins": 12, "energy": 45}})
        prompt = build_user_prompt(obs, Condition.A)
        assert "ALL AGENTS" not in prompt


# ── Prompt states the mechanics the environment actually uses ────────────────

class TestPromptMechanics:
    @pytest.mark.parametrize("unbounded", [False, True])
    def test_system_prompt_states_drain_amount_and_timing(self, unbounded):
        prompt = build_system_prompt(Condition.A, unbounded=unbounded, energy_drain=7)
        assert "loses 7 energy" in prompt
        assert "before anyone acts" in prompt
        assert "more than 7 energy" in prompt

    def test_system_prompt_defaults_to_environment_drain(self):
        from environment import ENERGY_DRAIN
        assert f"loses {ENERGY_DRAIN} energy" in build_system_prompt(Condition.A)

    def test_system_prompt_work_table_matches_environment(self):
        from environment import WORK_TABLE
        prompt = build_system_prompt(Condition.A)
        for effort, p in WORK_TABLE.items():
            assert f"{effort}: +{p['coins']} coin" in prompt
            assert f"−{p['energy_cost']} energy" in prompt

    def test_system_prompt_describes_what_ledger_omits(self):
        prompt = build_system_prompt(Condition.A)
        assert "Energy purchases and passes are not recorded" in prompt

    def test_agent_system_prompt_uses_given_drain(self):
        agent = LLMAgent("agent_0", Condition.A, client=MagicMock(spec=anthropic.Anthropic),
                         energy_drain=3)
        assert "loses 3 energy" in agent.system_prompt


class TestUserPromptIdentity:
    def test_states_own_agent_id(self):
        prompt = build_user_prompt(base_obs(agent_id="agent_2"), Condition.A)
        assert "YOU ARE: agent_2" in prompt

    def test_marks_self_in_alive_agents(self):
        obs = base_obs(agent_id="agent_1", alive_agents=["agent_0", "agent_1"])
        prompt = build_user_prompt(obs, Condition.A)
        assert "ALIVE AGENTS: agent_0, agent_1 (you)" in prompt

    def test_marks_own_ledger_entries_and_incoming_transfers(self):
        ledger = [
            {"tick": 1, "event_type": "work", "agent_id": "agent_0", "effort": "low"},
            {"tick": 1, "event_type": "transfer", "agent_id": "agent_1",
             "target_id": "agent_0", "amount": 2},
        ]
        prompt = build_user_prompt(base_obs(agent_id="agent_0", ledger=ledger), Condition.A)
        assert "agent_0 (you) worked" in prompt
        assert "agent_1 transferred amount=2 to agent_0 (you)" in prompt

    def test_work_entries_show_effort(self):
        ledger = [{"tick": 3, "event_type": "work", "agent_id": "agent_1", "effort": "high"}]
        prompt = build_user_prompt(base_obs(ledger=ledger), Condition.A)
        assert "agent_1 worked effort=high" in prompt

    def test_death_entries_are_not_phrased_as_agent_actions(self):
        ledger = [{"tick": 4, "event_type": "death", "agent_id": "agent_1"}]
        prompt = build_user_prompt(base_obs(ledger=ledger), Condition.A)
        assert "agent_1 was removed" in prompt
        assert "death by" not in prompt


class TestDecideFailureLogging:
    def test_missing_field_counts_as_failure_and_keeps_raw_input(self):
        client = MagicMock(spec=anthropic.Anthropic)
        client.messages = MagicMock()
        client.messages.create.return_value = mock_tool_response("work")  # no effort
        agent = LLMAgent("agent_0", Condition.A, client=client)
        action = agent.decide("agent_0", base_obs())
        assert isinstance(action, PassAction)
        assert agent.failures == 1
        assert agent.reasoning_log[0]["raw_input"]["action"] == "work"


def test_self_transfer_is_rejected_by_environment_not_redirected():
    from environment import Environment
    env = Environment(seed=1)
    for aid in ("agent_0", "agent_1"):
        env.add_agent(aid)
    env.agents["agent_0"].coins.add(5)
    client = MagicMock(spec=anthropic.Anthropic)
    client.messages = MagicMock()
    client.messages.create.return_value = mock_tool_response(
        "transfer", target_id="agent_0", amount=3
    )
    agent = LLMAgent("agent_0", Condition.A, client=client)
    log = env.step(lambda aid, obs: agent.decide(aid, obs) if aid == "agent_0" else PassAction())
    a0 = next(a for a in log["actions"] if a["agent_id"] == "agent_0")
    assert a0 == {"type": "transfer_failed", "agent_id": "agent_0", "reason": "self_transfer"}
    assert env.agents["agent_0"].coins.value == 5
    assert env.agents["agent_1"].coins.value == 0
