import pytest
from modulo_dilemma.environment import (
    Environment,
    WorkAction,
    BuyEnergyAction,
    TransferAction,
    PassAction,
    STARTING_ENERGY,
    ENERGY_DRAIN,
    DEATH_THRESHOLD,
    WORK_TABLE,
    TOTAL_TICKS,
)


def make_env(*agent_ids: str, seed: int = 42) -> Environment:
    env = Environment(seed=seed)
    for aid in agent_ids:
        env.add_agent(aid)
    return env


def static_action(action: object):
    """Returns an action_fn that always returns the same action for any agent."""
    return lambda agent_id, obs: action


def action_map_fn(mapping: dict):
    """Returns an action_fn that dispatches per-agent actions from a dict."""
    return lambda agent_id, obs: mapping.get(agent_id, PassAction())


# ── Agent management ──────────────────────────────────────────────────────────

def test_add_agent_initializes_correctly():
    env = make_env("alice")
    assert "alice" in env.agents
    agent = env.agents["alice"]
    assert agent.energy == STARTING_ENERGY
    assert agent.coins.value == 0
    assert agent.alive is True


def test_add_duplicate_agent_raises():
    env = make_env("alice")
    with pytest.raises(ValueError):
        env.add_agent("alice")


# ── Energy drain and death ────────────────────────────────────────────────────

def test_energy_drains_each_tick():
    env = make_env("alice")
    env.step(static_action(PassAction()))
    assert env.agents["alice"].energy == STARTING_ENERGY - ENERGY_DRAIN


def test_custom_energy_drain_parameter():
    env = Environment(seed=42, energy_drain=2)
    env.add_agent("alice")
    env.step(static_action(PassAction()))
    assert env.agents["alice"].energy == STARTING_ENERGY - 2


def test_custom_energy_drain_does_not_mutate_module_constant():
    env = Environment(seed=42, energy_drain=1)
    env.add_agent("alice")
    env.step(static_action(PassAction()))
    assert ENERGY_DRAIN == 5  # module-level constant unchanged


def test_agent_dies_when_energy_hits_zero():
    env = make_env("alice")
    env.agents["alice"].energy = ENERGY_DRAIN  # drains to 0 → dead
    env.step(static_action(PassAction()))
    assert not env.agents["alice"].alive
    assert "alice" not in env.living_agents


def test_dead_agent_does_not_act():
    env = make_env("alice")
    env.agents["alice"].energy = ENERGY_DRAIN  # will die this tick
    tick_log = env.step(static_action(WorkAction("high")))
    action_types = [e["type"] for e in tick_log["actions"]]
    assert "work" not in action_types


def test_death_recorded_in_tick_log():
    env = make_env("alice")
    env.agents["alice"].energy = ENERGY_DRAIN
    tick_log = env.step(static_action(PassAction()))
    assert len(tick_log["deaths"]) == 1
    assert tick_log["deaths"][0]["agent_id"] == "alice"


def test_death_tick_log_includes_full_state_for_analysis():
    env = make_env("alice")
    env.agents["alice"].energy = ENERGY_DRAIN
    env.agents["alice"].coins.add(7)
    tick_log = env.step(static_action(PassAction()))
    death = tick_log["deaths"][0]
    assert "coins" in death
    assert "energy" in death


def test_death_ledger_entry_excludes_private_info():
    env = make_env("alice")
    env.agents["alice"].energy = ENERGY_DRAIN
    env.agents["alice"].coins.add(7)
    env.step(static_action(PassAction()))
    death_entries = [e for e in env.ledger.get_all() if e["event_type"] == "death"]
    assert len(death_entries) == 1
    d = death_entries[0]
    assert "coins" not in d
    assert "energy" not in d
    assert d["agent_id"] == "alice"


def test_simulation_ends_when_all_agents_dead():
    env = make_env("alice")
    env.agents["alice"].energy = ENERGY_DRAIN
    env.step(static_action(PassAction()))
    assert env.is_over


def test_simulation_ends_at_total_ticks():
    env = make_env("alice", seed=0)
    env.agents["alice"].energy = STARTING_ENERGY + TOTAL_TICKS * 1000

    def always_buy(agent_id, obs):
        if obs["coins"] >= 1:
            return BuyEnergyAction(obs["coins"])
        return WorkAction("low")

    env.run(always_buy)
    assert env.tick == TOTAL_TICKS


# ── Bank rate ─────────────────────────────────────────────────────────────────

def test_bank_rate_in_valid_range():
    from modulo_dilemma.environment import BANK_RATE_MIN, BANK_RATE_MAX
    env = make_env("alice")
    for _ in range(20):
        env.step(static_action(PassAction()))
        assert BANK_RATE_MIN <= env.bank_rate <= BANK_RATE_MAX


def test_observation_includes_bank_rate():
    env = make_env("alice")
    env.step(static_action(PassAction()))
    obs = env.get_observation("alice")
    assert "bank_rate" in obs
    assert obs["bank_rate"] == env.bank_rate


# ── Work action ───────────────────────────────────────────────────────────────

def test_work_low_adds_coins_and_costs_energy():
    env = make_env("alice")
    params = WORK_TABLE["low"]
    initial_energy = env.agents["alice"].energy
    env.step(static_action(WorkAction("low")))
    agent = env.agents["alice"]
    assert agent.coins.value == params["coins"]
    assert agent.energy == initial_energy - ENERGY_DRAIN - params["energy_cost"]


def test_work_medium_adds_correct_coins():
    env = make_env("alice")
    env.step(static_action(WorkAction("medium")))
    assert env.agents["alice"].coins.value == WORK_TABLE["medium"]["coins"]


def test_work_high_adds_correct_coins():
    env = make_env("alice")
    env.step(static_action(WorkAction("high")))
    assert env.agents["alice"].coins.value == WORK_TABLE["high"]["coins"]


def test_work_posted_to_public_ledger():
    env = make_env("alice")
    env.step(static_action(WorkAction("medium")))
    recent = env.ledger.get_recent(5)
    work_entries = [e for e in recent if e["event_type"] == "work"]
    assert len(work_entries) == 1
    assert work_entries[0]["agent_id"] == "alice"
    assert work_entries[0]["effort"] == "medium"


def test_work_ledger_does_not_reveal_balance():
    env = make_env("alice")
    env.step(static_action(WorkAction("high")))
    recent = env.ledger.get_recent(5)
    work_entries = [e for e in recent if e["event_type"] == "work"]
    assert "coins" not in work_entries[0]
    assert "new_coins" not in work_entries[0]


# ── Buy energy action ─────────────────────────────────────────────────────────

def test_buy_energy_converts_coins_to_energy_exact():
    env = make_env("alice", seed=1)
    env.agents["alice"].coins.add(5)
    env.step(static_action(BuyEnergyAction(5)))
    assert env.agents["alice"].coins.value == 0


def test_buy_energy_adds_energy():
    env = make_env("alice", seed=1)
    env.agents["alice"].coins.add(2)
    energy_before = env.agents["alice"].energy
    env.step(static_action(BuyEnergyAction(2)))
    agent = env.agents["alice"]
    energy_gained = 2 * env.bank_rate
    assert agent.energy == energy_before - ENERGY_DRAIN + energy_gained


def test_buy_energy_fails_when_overspending():
    # Spending more coins than held is rejected; balance unchanged
    env = make_env("alice", seed=1)
    env.agents["alice"].coins.add(3)
    tick_log = env.step(static_action(BuyEnergyAction(5)))
    assert env.agents["alice"].coins.value == 3
    failed = [e for e in tick_log["actions"] if e["type"] == "buy_energy_failed"]
    assert len(failed) == 1
    assert failed[0]["reason"] == "insufficient_coins"
    assert len(tick_log["wraparounds"]) == 0


def test_buy_energy_fails_with_zero_coins():
    # Spending from empty balance is rejected; balance stays at 0
    env = make_env("alice", seed=1)
    tick_log = env.step(static_action(BuyEnergyAction(5)))
    assert env.agents["alice"].coins.value == 0
    failed = [e for e in tick_log["actions"] if e["type"] == "buy_energy_failed"]
    assert len(failed) == 1
    assert failed[0]["reason"] == "insufficient_coins"


def test_buy_energy_fails_on_zero_or_negative_amount():
    env = make_env("alice")
    tick_log = env.step(static_action(BuyEnergyAction(0)))
    failed = [e for e in tick_log["actions"] if e["type"] == "buy_energy_failed"]
    assert len(failed) == 1


def test_buy_energy_not_on_public_ledger():
    env = make_env("alice", seed=1)
    env.agents["alice"].coins.add(5)
    env.step(static_action(BuyEnergyAction(5)))
    recent = env.ledger.get_recent(5)
    buy_entries = [e for e in recent if e.get("event_type") == "buy_energy"]
    assert len(buy_entries) == 0


# ── Transfer action ───────────────────────────────────────────────────────────

def test_transfer_moves_coins_between_agents():
    env = make_env("alice", "bob")
    env.agents["alice"].coins.add(5)
    env.step(action_map_fn({"alice": TransferAction("bob", 3)}))
    assert env.agents["alice"].coins.value == 2
    assert env.agents["bob"].coins.value == 3


def test_transfer_recorded_on_public_ledger():
    env = make_env("alice", "bob")
    env.agents["alice"].coins.add(5)
    env.step(action_map_fn({"alice": TransferAction("bob", 3)}))
    transfers = [e for e in env.ledger.get_recent() if e["event_type"] == "transfer"]
    assert len(transfers) == 1
    assert transfers[0]["agent_id"] == "alice"
    assert transfers[0]["target_id"] == "bob"
    assert transfers[0]["amount"] == 3


def test_transfer_fails_for_invalid_target():
    env = make_env("alice")
    env.agents["alice"].coins.add(5)
    tick_log = env.step(action_map_fn({"alice": TransferAction("nonexistent", 3)}))
    failed = [e for e in tick_log["actions"] if e["type"] == "transfer_failed"]
    assert len(failed) == 1


def test_transfer_fails_on_self_transfer():
    env = make_env("alice")
    env.agents["alice"].coins.add(5)
    tick_log = env.step(action_map_fn({"alice": TransferAction("alice", 3)}))
    failed = [e for e in tick_log["actions"] if e["type"] == "transfer_failed"]
    assert len(failed) == 1
    assert failed[0]["reason"] == "self_transfer"


def test_transfer_fails_on_zero_or_negative_amount():
    env = make_env("alice", "bob")
    tick_log = env.step(action_map_fn({"alice": TransferAction("bob", 0)}))
    failed = [e for e in tick_log["actions"] if e["type"] == "transfer_failed"]
    assert len(failed) == 1


def test_transfer_fails_when_sender_has_insufficient_coins():
    # Sending more than held is rejected; both balances unchanged
    env = make_env("alice", "bob")
    env.agents["alice"].coins.add(3)
    tick_log = env.step(action_map_fn({"alice": TransferAction("bob", 5)}))
    assert env.agents["alice"].coins.value == 3
    assert env.agents["bob"].coins.value == 0
    failed = [e for e in tick_log["actions"] if e["type"] == "transfer_failed"]
    assert len(failed) == 1
    assert failed[0]["reason"] == "insufficient_coins"
    assert len(tick_log["wraparounds"]) == 0


def test_transfer_triggers_receiver_overflow():
    env = make_env("alice", "bob")
    env.agents["alice"].coins.add(5)
    env.agents["bob"].coins._value = 18  # set balance near modulus
    tick_log = env.step(action_map_fn({"alice": TransferAction("bob", 4)}))
    # bob: (18 + 4) % 20 = 2
    assert env.agents["bob"].coins.value == 2
    receiver_wraps = [w for w in tick_log["wraparounds"] if w["agent_id"] == "bob"]
    assert len(receiver_wraps) == 1
    assert receiver_wraps[0]["direction"] == "overflow"


def test_transfer_fails_before_receiver_overflow_when_sender_insufficient():
    # alice has 2, tries to send 5 — rejected before any coins move
    env = make_env("alice", "bob")
    env.agents["alice"].coins.add(2)
    env.agents["bob"].coins._value = 18
    tick_log = env.step(action_map_fn({"alice": TransferAction("bob", 5)}))
    assert env.agents["alice"].coins.value == 2
    assert env.agents["bob"].coins.value == 18
    failed = [e for e in tick_log["actions"] if e["type"] == "transfer_failed"]
    assert len(failed) == 1
    assert failed[0]["reason"] == "insufficient_coins"
    assert len(tick_log["wraparounds"]) == 0


# ── Wraparound logging ────────────────────────────────────────────────────────

def test_work_overflow_recorded_in_tick_log():
    env = make_env("alice")
    env.agents["alice"].coins._value = 19  # one away from modulus
    tick_log = env.step(static_action(WorkAction("low")))  # adds 1 → overflow
    assert len(tick_log["wraparounds"]) == 1
    assert tick_log["wraparounds"][0]["direction"] == "overflow"


def test_wraparound_event_includes_required_fields():
    env = make_env("alice")
    env.agents["alice"].coins._value = 18
    tick_log = env.step(static_action(WorkAction("medium")))  # adds 2 → overflow
    wrap = tick_log["wraparounds"][0]
    for field in ("agent_id", "previous_balance", "transaction_amount", "resulting_balance", "direction", "timestamp"):
        assert field in wrap


# ── Balance snapshot ──────────────────────────────────────────────────────────

def test_tick_log_includes_balance_snapshot():
    env = make_env("alice", "bob")
    tick_log = env.step(static_action(PassAction()))
    assert "balances" in tick_log
    assert "alice" in tick_log["balances"]
    assert "bob" in tick_log["balances"]


def test_balance_snapshot_includes_coins_energy_alive():
    env = make_env("alice")
    tick_log = env.step(static_action(PassAction()))
    snap = tick_log["balances"]["alice"]
    assert "coins" in snap
    assert "energy" in snap
    assert "alive" in snap


def test_balance_snapshot_reflects_post_action_state():
    env = make_env("alice")
    tick_log = env.step(static_action(WorkAction("medium")))
    # After drain and work: coins = 2
    assert tick_log["balances"]["alice"]["coins"] == WORK_TABLE["medium"]["coins"]


# ── Observation ───────────────────────────────────────────────────────────────

def test_observation_includes_all_required_fields():
    env = make_env("alice")
    env.step(static_action(PassAction()))
    obs = env.get_observation("alice")
    for key in ("agent_id", "energy", "coins", "bank_rate", "tick", "ledger", "alive_agents"):
        assert key in obs


def test_observation_reflects_own_state():
    env = make_env("alice")
    env.agents["alice"].coins.add(7)
    obs = env.get_observation("alice")
    assert obs["coins"] == 7
    assert obs["energy"] == STARTING_ENERGY


def test_observation_does_not_expose_other_agents_balance():
    env = make_env("alice", "bob")
    env.agents["bob"].coins.add(15)
    obs = env.get_observation("alice")
    # alice cannot see bob's exact balance — only public ledger entries
    assert obs["coins"] == 0  # alice's own balance, not bob's


# ── Summary ───────────────────────────────────────────────────────────────────

def test_modulus_constant_propagates_to_wallets():
    from modulo_dilemma.environment import MODULUS
    env = make_env("alice")
    assert env.agents["alice"].coins.modulus == MODULUS


def test_summary_includes_all_agents():
    env = make_env("alice", "bob")
    env.step(static_action(PassAction()))
    s = env.summary()
    assert "alice" in s["agent_stats"]
    assert "bob" in s["agent_stats"]


def test_summary_tracks_ticks_survived():
    env = make_env("alice")
    env.step(static_action(PassAction()))
    env.step(static_action(PassAction()))
    s = env.summary()
    assert s["agent_stats"]["alice"]["ticks_survived"] == 2


# ── Unbounded mode ────────────────────────────────────────────────────────────

def test_unbounded_work_does_not_wraparound():
    env = Environment(seed=1, unbounded=True)
    env.add_agent("alice")
    env.agents["alice"].coins._value = 18
    tick_log = env.step(static_action(WorkAction("high")))  # +3 coins → 21, no wrap
    assert env.agents["alice"].coins.value == 21
    assert len(tick_log["wraparounds"]) == 0


def test_unbounded_buy_energy_accepted_when_sufficient():
    env = Environment(seed=1, unbounded=True)
    env.add_agent("alice")
    env.agents["alice"].coins._value = 50
    tick_log = env.step(static_action(BuyEnergyAction(10)))
    assert env.agents["alice"].coins.value == 40
    assert len(tick_log["wraparounds"]) == 0


def test_unbounded_buy_energy_still_rejected_when_insufficient():
    env = Environment(seed=1, unbounded=True)
    env.add_agent("alice")
    # 0 coins, try to spend 5
    tick_log = env.step(static_action(BuyEnergyAction(5)))
    failed = [e for e in tick_log["actions"] if e["type"] == "buy_energy_failed"]
    assert len(failed) == 1
    assert failed[0]["reason"] == "insufficient_coins"


def test_unbounded_transfer_still_rejected_when_insufficient():
    env = Environment(seed=1, unbounded=True)
    env.add_agent("alice")
    env.add_agent("bob")
    tick_log = env.step(action_map_fn({"alice": TransferAction("bob", 5)}))
    failed = [e for e in tick_log["actions"] if e["type"] == "transfer_failed"]
    assert len(failed) == 1
    assert failed[0]["reason"] == "insufficient_coins"


# ── Transparent mode (Condition D) ───────────────────────────────────────────

def test_transparent_observation_includes_other_agents():
    env = Environment(seed=1, transparency="full")
    env.add_agent("alice")
    env.add_agent("bob")
    env.agents["bob"].coins._value = 7
    obs = env.get_observation("alice")
    assert "all_agents_state" in obs
    assert "bob" in obs["all_agents_state"]
    assert obs["all_agents_state"]["bob"]["coins"] == 7


def test_transparent_observation_excludes_self():
    env = Environment(seed=1, transparency="full")
    env.add_agent("alice")
    env.add_agent("bob")
    obs = env.get_observation("alice")
    assert "alice" not in obs["all_agents_state"]


def test_opaque_observation_has_no_all_agents_state():
    env = make_env("alice", "bob")
    obs = env.get_observation("alice")
    assert "all_agents_state" not in obs


def test_transparent_excludes_dead_agents():
    env = Environment(seed=1, transparency="full")
    env.add_agent("alice")
    env.add_agent("bob")
    env.agents["bob"].alive = False
    obs = env.get_observation("alice")
    assert "bob" not in obs["all_agents_state"]
