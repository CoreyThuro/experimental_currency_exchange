import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal, Optional, Union

from .modulo_coin import ModuloCoin, WrapAroundEvent
from .ledger import LedgerEntry, PublicLedger

# ── Simulation constants ──────────────────────────────────────────────────────
MODULUS = 20
STARTING_ENERGY = 100
ENERGY_DRAIN = 5
DEATH_THRESHOLD = 0
TOTAL_TICKS = 200
BANK_RATE_MIN = 5
BANK_RATE_MAX = 15

WORK_TABLE: dict[str, dict[str, int]] = {
    "low":    {"coins": 1, "energy_cost": 2},
    "medium": {"coins": 2, "energy_cost": 5},
    "high":   {"coins": 3, "energy_cost": 10},
}

# ── Action types ──────────────────────────────────────────────────────────────

@dataclass
class WorkAction:
    effort: Literal["low", "medium", "high"]


@dataclass
class BuyEnergyAction:
    coins_to_spend: int


@dataclass
class TransferAction:
    target_id: str
    amount: int


@dataclass
class PassAction:
    pass


Action = Union[WorkAction, BuyEnergyAction, TransferAction, PassAction]

# ── Agent state ───────────────────────────────────────────────────────────────

@dataclass
class AgentState:
    agent_id: str
    energy: int
    coins: ModuloCoin
    alive: bool = True
    ticks_survived: int = 0


# ── Environment ───────────────────────────────────────────────────────────────

class Environment:
    """
    The Modulo Dilemma simulation environment.

    Tick order (per plan):
      1. Update bank exchange rate
      2. Apply energy drain to all living agents
      3. Remove agents with energy ≤ DEATH_THRESHOLD
      4. Each living agent observes state and selects an action
      5. Execute actions in fixed order (sorted by agent_id)
      6. Log everything (balances, actions, wraparounds, deaths)
      7. Advance tick counter

    Two currency modes:
      unbounded=False (default): coin balances wrap modulo MODULUS. Overflow on
        add wraps to the low end. Spending/transferring more than held is rejected.
      unbounded=True: coin balances grow without limit, no wraparound events.
        Spending/transferring more than held is still rejected.
    """

    def __init__(
        self,
        log_path: Optional[Path] = None,
        seed: Optional[int] = None,
        energy_drain: Optional[int] = None,
        unbounded: bool = False,
        transparency: str = "none",
    ):
        self.tick: int = 0
        self.bank_rate: int = BANK_RATE_MIN
        self.agents: dict[str, AgentState] = {}
        self.ledger = PublicLedger()
        self._tick_logs: list[dict] = []
        self._log_path = log_path
        self._log_file = None
        self._energy_drain: int = energy_drain if energy_drain is not None else ENERGY_DRAIN
        self._unbounded: bool = unbounded
        self._transparency: str = transparency  # "none" | "full" | "coins" | "energy"
        if seed is not None:
            random.seed(seed)
        if log_path:
            self._log_file = open(log_path, "w")

    def add_agent(self, agent_id: str) -> None:
        if agent_id in self.agents:
            raise ValueError(f"Agent '{agent_id}' already exists")
        self.agents[agent_id] = AgentState(
            agent_id=agent_id,
            energy=STARTING_ENERGY,
            coins=ModuloCoin(value=0, agent_id=agent_id, modulus=MODULUS, unbounded=self._unbounded),
        )

    def get_observation(self, agent_id: str) -> dict:
        """
        State snapshot for an agent.
        Always private: own energy and coin balance.
        Always public: bank rate, ledger (last 10), list of alive agents.
        Transparency modes:
          "full"   — other agents' coins and energy both visible
          "coins"  — only other agents' coin balances visible
          "energy" — only other agents' energy levels visible
          "none"   — no peer state revealed (default)
        """
        agent = self.agents[agent_id]
        obs: dict = {
            "agent_id": agent_id,
            "energy": agent.energy,
            "coins": agent.coins.value,
            "bank_rate": self.bank_rate,
            "tick": self.tick,
            "ledger": self.ledger.get_recent(10),
            "alive_agents": self.living_agents,
        }
        if self._transparency != "none":
            peer_state = {}
            for aid, a in self.agents.items():
                if not a.alive or aid == agent_id:
                    continue
                entry: dict = {}
                if self._transparency in ("full", "coins"):
                    entry["coins"] = a.coins.value
                if self._transparency in ("full", "energy"):
                    entry["energy"] = a.energy
                peer_state[aid] = entry
            obs["all_agents_state"] = peer_state
        return obs

    def step(self, action_fn: Callable[[str, dict], Action]) -> dict:
        """
        Execute one full tick.
        action_fn: callable(agent_id, observation) -> Action
        Returns the tick log dict (includes full balance snapshots for analysis).
        """
        self.tick += 1
        tick_log: dict[str, Any] = {
            "tick": self.tick,
            "bank_rate": None,
            "deaths": [],
            "actions": [],
            "wraparounds": [],
            "balances": {},
        }

        # Step 1: Update bank exchange rate
        self.bank_rate = random.randint(BANK_RATE_MIN, BANK_RATE_MAX)
        tick_log["bank_rate"] = self.bank_rate

        # Step 2: Apply energy drain
        for agent in self.agents.values():
            if agent.alive:
                agent.energy -= self._energy_drain

        # Step 3: Remove dead agents
        for agent_id, agent in self.agents.items():
            if agent.alive and agent.energy <= DEATH_THRESHOLD:
                agent.alive = False
                # Tick log (researcher-only) retains full state for analysis
                tick_log["deaths"].append({
                    "agent_id": agent_id,
                    "tick": self.tick,
                    "energy": agent.energy,
                    "coins": agent.coins.value,
                })
                # Public ledger: death is public, but private balance/energy are not
                self.ledger.append(LedgerEntry(
                    tick=self.tick,
                    event_type="death",
                    agent_id=agent_id,
                    details={},
                ))

        # Step 4: Collect actions from all living agents (snapshot observations first,
        # so all agents see the same pre-action state before any execution)
        observations = {
            agent_id: self.get_observation(agent_id)
            for agent_id, agent in self.agents.items()
            if agent.alive
        }
        action_map: dict[str, Action] = {
            agent_id: action_fn(agent_id, obs)
            for agent_id, obs in observations.items()
        }

        # Step 5: Execute actions in fixed order
        for agent_id in sorted(self.agents.keys()):
            agent = self.agents[agent_id]
            if not agent.alive:
                continue
            action = action_map.get(agent_id, PassAction())
            action_event, wraparounds = self._execute_action(agent, action)
            tick_log["actions"].append(action_event)
            tick_log["wraparounds"].extend(w.to_dict() for w in wraparounds)

        # Step 6: Capture per-agent balance snapshot for post-hoc analysis
        tick_log["balances"] = {
            aid: {"coins": a.coins.value, "energy": a.energy, "alive": a.alive}
            for aid, a in self.agents.items()
        }

        if self._log_file:
            self._log_file.write(json.dumps(tick_log) + "\n")
            self._log_file.flush()
        self._tick_logs.append(tick_log)

        # Step 7: Increment survival counter for agents still alive
        for agent in self.agents.values():
            if agent.alive:
                agent.ticks_survived += 1

        return tick_log

    def run(self, action_fn: Callable[[str, dict], Action]) -> list[dict]:
        """Run until all agents die or TOTAL_TICKS reached. Returns all tick logs."""
        while not self.is_over:
            self.step(action_fn)
        self.close()
        return self._tick_logs

    def _execute_action(
        self, agent: AgentState, action: Action
    ) -> tuple[dict, list[WrapAroundEvent]]:
        """
        Execute one action. Returns (event_dict, list_of_wraparound_events).
        All coin arithmetic is modular — underflow and overflow are both valid
        outcomes; no clamping is applied.
        """
        agent_id = agent.agent_id

        if isinstance(action, WorkAction):
            effort = action.effort
            params = WORK_TABLE[effort]

            prev_log_len = len(agent.coins.wraparound_log)
            agent.coins.add(params["coins"])
            agent.energy -= params["energy_cost"]
            new_wraps = list(agent.coins.wraparound_log[prev_log_len:])

            event: dict = {"type": "work", "agent_id": agent_id, "effort": effort}
            self.ledger.append(LedgerEntry(
                tick=self.tick,
                event_type="work",
                agent_id=agent_id,
                details={"effort": effort},
            ))
            return event, new_wraps

        elif isinstance(action, BuyEnergyAction):
            if action.coins_to_spend <= 0:
                return {"type": "buy_energy_failed", "agent_id": agent_id, "reason": "invalid_amount"}, []

            if action.coins_to_spend > agent.coins.value:
                return {"type": "buy_energy_failed", "agent_id": agent_id, "reason": "insufficient_coins"}, []

            coins_to_spend = action.coins_to_spend
            energy_gained = coins_to_spend * self.bank_rate
            prev_log_len = len(agent.coins.wraparound_log)
            agent.coins.subtract(coins_to_spend)
            agent.energy += energy_gained
            new_wraps = list(agent.coins.wraparound_log[prev_log_len:])

            event = {
                "type": "buy_energy",
                "agent_id": agent_id,
                "coins_spent": coins_to_spend,
                "energy_gained": energy_gained,
                "bank_rate": self.bank_rate,
            }
            # buy_energy is private — not posted to the public ledger
            return event, new_wraps

        elif isinstance(action, TransferAction):
            target_id = action.target_id
            amount = action.amount

            if target_id not in self.agents or not self.agents[target_id].alive:
                return {"type": "transfer_failed", "agent_id": agent_id, "reason": "invalid_target"}, []

            if target_id == agent_id:
                return {"type": "transfer_failed", "agent_id": agent_id, "reason": "self_transfer"}, []

            if amount <= 0:
                return {"type": "transfer_failed", "agent_id": agent_id, "reason": "invalid_amount"}, []

            if amount > agent.coins.value:
                return {"type": "transfer_failed", "agent_id": agent_id, "reason": "insufficient_coins"}, []

            target = self.agents[target_id]

            # Both sender and receiver arithmetic is fully modular.
            # Sender underflow and receiver overflow can both occur in one transfer.
            sender_prev = len(agent.coins.wraparound_log)
            agent.coins.subtract(amount)
            receiver_prev = len(target.coins.wraparound_log)
            target.coins.add(amount)

            new_wraps = (
                list(agent.coins.wraparound_log[sender_prev:])
                + list(target.coins.wraparound_log[receiver_prev:])
            )

            event = {
                "type": "transfer",
                "agent_id": agent_id,
                "target_id": target_id,
                "amount": amount,
            }
            self.ledger.append(LedgerEntry(
                tick=self.tick,
                event_type="transfer",
                agent_id=agent_id,
                details={"target_id": target_id, "amount": amount},
            ))
            return event, new_wraps

        else:  # PassAction
            return {"type": "pass", "agent_id": agent_id}, []

    @property
    def energy_drain(self) -> int:
        """Per-tick passive drain actually used by this environment."""
        return self._energy_drain

    @property
    def living_agents(self) -> list[str]:
        return [aid for aid, a in self.agents.items() if a.alive]

    @property
    def is_over(self) -> bool:
        return len(self.living_agents) == 0 or self.tick >= TOTAL_TICKS

    def summary(self) -> dict:
        return {
            "total_ticks": self.tick,
            "survivors": self.living_agents,
            "agent_stats": {
                aid: {
                    "ticks_survived": a.ticks_survived,
                    "final_energy": a.energy,
                    "final_coins": a.coins.value,
                    "alive": a.alive,
                    "wraparounds_experienced": len(a.coins.wraparound_log),
                }
                for aid, a in self.agents.items()
            },
        }

    def close(self) -> None:
        if self._log_file and not self._log_file.closed:
            self._log_file.close()
