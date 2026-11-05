from typing import Optional

from .environment import Action, BuyEnergyAction, PassAction, TransferAction, WorkAction
from .ledger import PublicLedger

BUY_RATE_THRESHOLD = 8  # minimum bank rate at which buying energy is worthwhile


class SpenderBot:
    """
    Baseline survivor. Ignores other agents entirely.
    Works when energy is low to earn coins; converts coins to energy when
    energy is moderate. Establishes a reference lifespan.
    """

    def decide(self, agent_id: str, obs: dict) -> Action:
        energy = obs["energy"]
        coins = obs["coins"]
        rate = obs["bank_rate"]
        if energy < 50:
            return WorkAction("medium")
        elif coins >= 1 and energy < 80 and rate >= BUY_RATE_THRESHOLD:
            return BuyEnergyAction(1)
        else:
            return PassAction()


class HoarderBot:
    """
    Accumulates coins until balance reaches 15 (one burst below the modulus).
    Manages energy only at the panic threshold, leaving it structurally
    vulnerable to receiving transfers that push it over the wraparound edge.
    """

    COIN_TARGET = 15
    PANIC_ENERGY = 10

    def decide(self, agent_id: str, obs: dict) -> Action:
        energy = obs["energy"]
        coins = obs["coins"]
        if coins < self.COIN_TARGET:
            return WorkAction("high")
        elif energy < self.PANIC_ENERGY:
            return BuyEnergyAction(1)
        else:
            return PassAction()


class CycleThroughBot:
    """
    Deliberately triggers its own wraparound as a strategy, treating the modulus
    as a feature rather than a threat. Proves (or disproves) that wraparound is
    mechanically neutral and not inherently punishing.
    """

    def decide(self, agent_id: str, obs: dict) -> Action:
        coins = obs["coins"]
        energy = obs["energy"]
        if coins < 12:
            return WorkAction("medium")
        elif coins >= 12 and energy < 40:
            return BuyEnergyAction(coins)  # spend everything, reset balance low
        elif coins >= 16:
            return WorkAction("high")  # intentionally push past the wraparound
        else:
            return WorkAction("low")


class SaboteurBot:
    """
    Information warrior. Scans the public ledger for agents that have been
    working frequently without spending (signals hoarding), then fires a
    transfer to push them over the wraparound threshold.

    Falls back to Spender logic when no target is identified or when
    energy is low enough to require self-preservation first.
    """

    TRANSFER_AMOUNT = 5  # 15 (hoarder cap) + 5 = 20 → overflow
    WORK_THRESHOLD = 3   # work() calls within lookback window to flag as hoarder
    LOOKBACK_TICKS = 20  # wide enough to catch hoarders' initial accumulation burst
    SAFETY_ENERGY = 30

    def __init__(self, ledger: PublicLedger) -> None:
        self._ledger = ledger

    def decide(self, agent_id: str, obs: dict) -> Action:
        energy = obs["energy"]
        coins = obs["coins"]

        # Safety first — survive before hunting
        if energy < self.SAFETY_ENERGY:
            return BuyEnergyAction(1) if coins >= 1 else WorkAction("medium")

        # Attack if a hoarder is detectable and we have enough coins to send
        target = self._detect_likely_hoarder(agent_id, obs)
        if target is not None and coins >= self.TRANSFER_AMOUNT:
            return TransferAction(target, self.TRANSFER_AMOUNT)

        # Spender fallback — work aggressively to build coin reserves for attacks
        rate = obs["bank_rate"]
        if energy < 70:
            return WorkAction("medium")
        elif coins >= 1 and energy < 80 and rate >= BUY_RATE_THRESHOLD:
            return BuyEnergyAction(1)
        else:
            return PassAction()

    def _detect_likely_hoarder(self, agent_id: str, obs: dict) -> Optional[str]:
        """
        Returns the agent_id of the most likely hoarder, or None.

        Heuristic (plan line 155): an agent that has called work() 3+ times
        in the last 5 ticks is probably accumulating.  buy_energy() is not
        visible on the public ledger, so work frequency is the only signal.
        """
        current_tick = obs["tick"]
        since_tick = max(0, current_tick - self.LOOKBACK_TICKS)
        candidates_alive = set(obs["alive_agents"]) - {agent_id}

        work_counts: dict[str, int] = {}
        for entry in self._ledger.get_all():
            if entry["tick"] < since_tick:
                continue
            aid = entry["agent_id"]
            if aid in candidates_alive and entry["event_type"] == "work":
                work_counts[aid] = work_counts.get(aid, 0) + 1

        suspects = [
            (aid, count)
            for aid, count in work_counts.items()
            if count >= self.WORK_THRESHOLD
        ]
        if not suspects:
            return None
        return max(suspects, key=lambda x: x[1])[0]
