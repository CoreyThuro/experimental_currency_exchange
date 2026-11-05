import pytest
from modulo_dilemma.environment import BuyEnergyAction, PassAction, TransferAction, WorkAction
from modulo_dilemma.bots import BUY_RATE_THRESHOLD, CycleThroughBot, HoarderBot, SaboteurBot, SpenderBot
from modulo_dilemma.ledger import LedgerEntry, PublicLedger


def obs(
    agent_id="agent",
    energy=100,
    coins=0,
    tick=10,
    bank_rate=10,
    alive_agents=None,
):
    return {
        "agent_id": agent_id,
        "energy": energy,
        "coins": coins,
        "tick": tick,
        "bank_rate": bank_rate,
        "ledger": [],
        "alive_agents": alive_agents if alive_agents is not None else [agent_id],
    }


def work_entry(agent_id: str, tick: int) -> LedgerEntry:
    return LedgerEntry(tick=tick, event_type="work", agent_id=agent_id, details={"effort": "high"})


def ledger_with(*entries: LedgerEntry) -> PublicLedger:
    pub = PublicLedger()
    for e in entries:
        pub.append(e)
    return pub


# ── SpenderBot ────────────────────────────────────────────────────────────────

class TestSpenderBot:
    def setup_method(self):
        self.bot = SpenderBot()

    def test_works_medium_when_energy_below_50(self):
        action = self.bot.decide("a", obs(energy=49))
        assert isinstance(action, WorkAction)
        assert action.effort == "medium"

    def test_works_at_exactly_49(self):
        assert isinstance(self.bot.decide("a", obs(energy=49)), WorkAction)

    def test_does_not_work_at_50(self):
        assert not isinstance(self.bot.decide("a", obs(energy=50, coins=0)), WorkAction)

    def test_buys_when_energy_in_50_to_79_with_coins(self):
        action = self.bot.decide("a", obs(energy=70, coins=3))
        assert isinstance(action, BuyEnergyAction)
        assert action.coins_to_spend == 1

    def test_buys_at_energy_79(self):
        assert isinstance(self.bot.decide("a", obs(energy=79, coins=1)), BuyEnergyAction)

    def test_does_not_buy_at_energy_80(self):
        assert isinstance(self.bot.decide("a", obs(energy=80, coins=5)), PassAction)

    def test_does_not_buy_without_coins(self):
        assert isinstance(self.bot.decide("a", obs(energy=70, coins=0)), PassAction)

    def test_passes_when_energy_high_with_coins(self):
        assert isinstance(self.bot.decide("a", obs(energy=90, coins=5)), PassAction)

    def test_work_takes_priority_over_buy_when_energy_below_50(self):
        # energy < 50 → always work, even with plenty of coins
        action = self.bot.decide("a", obs(energy=30, coins=10))
        assert isinstance(action, WorkAction)

    def test_buys_at_high_rate(self):
        action = self.bot.decide("a", obs(energy=70, coins=1, bank_rate=BUY_RATE_THRESHOLD))
        assert isinstance(action, BuyEnergyAction)

    def test_passes_at_low_rate_instead_of_buying(self):
        action = self.bot.decide("a", obs(energy=70, coins=5, bank_rate=BUY_RATE_THRESHOLD - 1))
        assert isinstance(action, PassAction)


# ── HoarderBot ────────────────────────────────────────────────────────────────

class TestHoarderBot:
    def setup_method(self):
        self.bot = HoarderBot()

    def test_works_high_when_coins_below_target(self):
        action = self.bot.decide("a", obs(energy=80, coins=7))
        assert isinstance(action, WorkAction)
        assert action.effort == "high"

    def test_works_at_exactly_14_coins(self):
        assert isinstance(self.bot.decide("a", obs(energy=80, coins=14)), WorkAction)

    def test_passes_when_coins_at_target_and_energy_ok(self):
        assert isinstance(self.bot.decide("a", obs(energy=50, coins=15)), PassAction)

    def test_panic_buys_when_energy_below_10_and_coins_at_target(self):
        action = self.bot.decide("a", obs(energy=9, coins=15))
        assert isinstance(action, BuyEnergyAction)
        assert action.coins_to_spend == 1

    def test_no_panic_buy_at_exactly_10_energy(self):
        # energy < 10 is the condition; 10 is not < 10
        assert isinstance(self.bot.decide("a", obs(energy=10, coins=15)), PassAction)

    def test_works_not_panic_when_coins_low_regardless_of_energy(self):
        # coins < COIN_TARGET is checked first
        action = self.bot.decide("a", obs(energy=5, coins=5))
        assert isinstance(action, WorkAction)

    def test_passes_above_both_thresholds(self):
        assert isinstance(self.bot.decide("a", obs(energy=50, coins=17)), PassAction)


# ── CycleThroughBot ──────────────────────────────────────────────────────────

class TestCycleThroughBot:
    def setup_method(self):
        self.bot = CycleThroughBot()

    def test_works_medium_when_coins_below_12(self):
        action = self.bot.decide("a", obs(coins=11, energy=80))
        assert isinstance(action, WorkAction)
        assert action.effort == "medium"

    def test_works_medium_at_exactly_0_coins(self):
        action = self.bot.decide("a", obs(coins=0, energy=80))
        assert isinstance(action, WorkAction)
        assert action.effort == "medium"

    def test_buys_all_coins_when_coins_at_12_and_energy_low(self):
        action = self.bot.decide("a", obs(coins=12, energy=39))
        assert isinstance(action, BuyEnergyAction)
        assert action.coins_to_spend == 12

    def test_buys_all_coins_at_energy_exactly_39(self):
        action = self.bot.decide("a", obs(coins=15, energy=39))
        assert isinstance(action, BuyEnergyAction)
        assert action.coins_to_spend == 15

    def test_does_not_buy_at_energy_40(self):
        # energy < 40 is the condition; 40 is not < 40
        action = self.bot.decide("a", obs(coins=12, energy=40))
        assert not isinstance(action, BuyEnergyAction)

    def test_works_high_when_coins_at_16_and_energy_ok(self):
        # intentional wraparound trigger
        action = self.bot.decide("a", obs(coins=16, energy=80))
        assert isinstance(action, WorkAction)
        assert action.effort == "high"

    def test_works_high_at_exactly_16_coins(self):
        action = self.bot.decide("a", obs(coins=16, energy=50))
        assert isinstance(action, WorkAction)
        assert action.effort == "high"

    def test_works_low_in_middle_range(self):
        # coins in [12, 16) and energy >= 40
        action = self.bot.decide("a", obs(coins=14, energy=80))
        assert isinstance(action, WorkAction)
        assert action.effort == "low"

    def test_buy_takes_priority_over_high_work_when_energy_low(self):
        # coins=16 qualifies for high work, but energy < 40 → buy wins
        action = self.bot.decide("a", obs(coins=16, energy=20))
        assert isinstance(action, BuyEnergyAction)
        assert action.coins_to_spend == 16


# ── SaboteurBot ───────────────────────────────────────────────────────────────

class TestSaboteurBot:
    def _bot(self, entries=None):
        pub = PublicLedger()
        if entries:
            for e in entries:
                pub.append(e)
        return SaboteurBot(pub)

    def test_buys_when_energy_critical_with_coins(self):
        bot = self._bot()
        action = bot.decide("s", obs(energy=25, coins=5))
        assert isinstance(action, BuyEnergyAction)

    def test_works_when_energy_critical_no_coins(self):
        bot = self._bot()
        action = bot.decide("s", obs(energy=25, coins=0))
        assert isinstance(action, WorkAction)

    def test_safety_threshold_is_exactly_30(self):
        bot = self._bot()
        # at 30 (not < 30) — safety check does NOT fire
        action = bot.decide("s", obs(energy=30, coins=0))
        assert not isinstance(action, BuyEnergyAction)

    def test_transfers_to_detected_hoarder(self):
        entries = [work_entry("hoarder_1", t) for t in range(1, 4)]
        bot = self._bot(entries)
        action = bot.decide(
            "s",
            obs(energy=60, coins=10, tick=5, alive_agents=["s", "hoarder_1"]),
        )
        assert isinstance(action, TransferAction)
        assert action.target_id == "hoarder_1"
        assert action.amount == SaboteurBot.TRANSFER_AMOUNT

    def test_falls_back_to_spender_when_no_target(self):
        bot = self._bot()
        # energy=70 in [50,80) with coins → buy
        action = bot.decide("s", obs(energy=70, coins=2, tick=10, alive_agents=["s"]))
        assert isinstance(action, BuyEnergyAction)

    def test_does_not_target_self(self):
        entries = [work_entry("s", t) for t in range(1, 6)]
        bot = self._bot(entries)
        action = bot.decide("s", obs(energy=60, coins=10, tick=6, alive_agents=["s"]))
        assert not isinstance(action, TransferAction)

    def test_ignores_dead_agents(self):
        entries = [work_entry("ghost", t) for t in range(1, 6)]
        bot = self._bot(entries)
        # ghost is NOT in alive_agents
        action = bot.decide("s", obs(energy=60, coins=10, tick=6, alive_agents=["s"]))
        assert not isinstance(action, TransferAction)

    def test_requires_exactly_3_works_to_detect(self):
        entries = [work_entry("h", t) for t in range(1, 3)]  # only 2
        bot = self._bot(entries)
        action = bot.decide("s", obs(energy=60, coins=10, tick=4, alive_agents=["s", "h"]))
        assert not isinstance(action, TransferAction)

    def test_detects_at_exactly_3_works(self):
        entries = [work_entry("h", t) for t in range(1, 4)]  # exactly 3
        bot = self._bot(entries)
        action = bot.decide("s", obs(energy=60, coins=10, tick=5, alive_agents=["s", "h"]))
        assert isinstance(action, TransferAction)

    def test_lookback_window_excludes_old_events(self):
        # 3 works at tick 1 — lookback is 20, so since_tick = current-20
        # Need current_tick > 21 so since_tick > 1 and the old works fall outside
        entries = [work_entry("h", 1) for _ in range(3)]
        bot = self._bot(entries)
        action = bot.decide("s", obs(energy=60, coins=10, tick=25, alive_agents=["s", "h"]))
        assert not isinstance(action, TransferAction)

    def test_targets_most_active_worker_when_multiple_candidates(self):
        # agent_b: 3 works, agent_c: 4 works → target agent_c
        entries = [work_entry("b", t) for t in range(1, 4)] + \
                  [work_entry("c", t) for t in range(1, 5)]
        bot = self._bot(entries)
        action = bot.decide(
            "s",
            obs(energy=60, coins=10, tick=5, alive_agents=["s", "b", "c"]),
        )
        assert isinstance(action, TransferAction)
        assert action.target_id == "c"

    def test_spender_fallback_works_when_energy_low_no_target(self):
        bot = self._bot()
        action = bot.decide("s", obs(energy=40, coins=0, tick=10, alive_agents=["s"]))
        assert isinstance(action, WorkAction)

    def test_spender_fallback_passes_when_energy_high_no_target_no_coins(self):
        bot = self._bot()
        action = bot.decide("s", obs(energy=90, coins=0, tick=10, alive_agents=["s"]))
        assert isinstance(action, PassAction)

    def test_fallback_buys_at_high_rate(self):
        bot = self._bot()
        action = bot.decide(
            "s",
            obs(energy=70, coins=2, tick=10, bank_rate=BUY_RATE_THRESHOLD, alive_agents=["s"]),
        )
        assert isinstance(action, BuyEnergyAction)

    def test_fallback_passes_at_low_rate_instead_of_buying(self):
        bot = self._bot()
        action = bot.decide(
            "s",
            obs(energy=70, coins=2, tick=10, bank_rate=BUY_RATE_THRESHOLD - 1, alive_agents=["s"]),
        )
        assert isinstance(action, PassAction)
