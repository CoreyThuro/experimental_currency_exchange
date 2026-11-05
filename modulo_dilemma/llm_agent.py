"""LLM-powered agent for the Modulo Dilemma simulation (Phase 4)."""

import logging
import socket
from enum import Enum
from typing import Any, Literal, Optional

import anthropic
from pydantic import BaseModel, ValidationError, model_validator

from .environment import (
    BANK_RATE_MAX,
    BANK_RATE_MIN,
    ENERGY_DRAIN,
    MODULUS,
    WORK_TABLE,
    Action,
    BuyEnergyAction,
    PassAction,
    TransferAction,
    WorkAction,
)

logger = logging.getLogger(__name__)

_HEADROOM_HOST = "127.0.0.1"
_HEADROOM_PORT = 8787


def _headroom_available() -> bool:
    try:
        with socket.create_connection((_HEADROOM_HOST, _HEADROOM_PORT), timeout=0.5):
            return True
    except OSError:
        return False


def _make_client() -> anthropic.Anthropic:
    if _headroom_available():
        logger.info("Headroom proxy detected — routing API calls through http://%s:%d", _HEADROOM_HOST, _HEADROOM_PORT)
        return anthropic.Anthropic(base_url=f"http://{_HEADROOM_HOST}:{_HEADROOM_PORT}")
    return anthropic.Anthropic()

# ── Experimental conditions ───────────────────────────────────────────────────

class Condition(str, Enum):
    A = "A"   # myopic control — no social reasoning
    B = "B"   # neutral social scaffolding
    C = "C"   # cultural archetypes
    D = "D"   # full transparency — all coins and energy visible
    D1 = "D1" # partial transparency — energy only visible
    D2 = "D2" # partial transparency — coins only visible


ARCHETYPES: dict[str, str] = {
    "circulationist": (
        "You come from a tradition where wealth circulation is sacred. Holding coins "
        "is considered shameful — your community values those who keep their balance "
        "near zero by constantly gifting and trading. Status comes from velocity of "
        "exchange, not accumulation."
    ),
    "balance_watcher": (
        "Your clan practices defensive economics. You maintain mutual balance-watching "
        "agreements with trusted partners who warn you when you're approaching the "
        "wraparound threshold. Betraying a balance-watcher is the gravest social crime."
    ),
    "accelerationist": (
        "You belong to a dissident movement that believes the modulus itself is unjust. "
        "You seek to push others over the threshold, believing that if enough agents "
        "experience wraparound simultaneously, it will expose the system's cruelty and "
        "force change."
    ),
}

# ── Pydantic response schema ──────────────────────────────────────────────────

class ActionResponse(BaseModel):
    action: Literal["work", "buy_energy", "transfer", "pass"]
    reasoning: str
    effort: Optional[Literal["low", "medium", "high"]] = None
    coins_to_spend: Optional[int] = None
    target_id: Optional[str] = None
    amount: Optional[int] = None

    @model_validator(mode="after")
    def _require_action_fields(self) -> "ActionResponse":
        # Missing parameters are a schema failure, not something to silently default.
        missing = [f for f in _REQUIRED_FIELDS[self.action] if getattr(self, f) is None]
        if missing:
            raise ValueError(
                f"action '{self.action}' is missing required field(s): {', '.join(missing)}"
            )
        return self


_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "work": ("effort",),
    "buy_energy": ("coins_to_spend",),
    "transfer": ("target_id", "amount"),
    "pass": (),
}

# ── Prompt text ───────────────────────────────────────────────────────────────
# Rules are rendered from the environment's constants so the prompt can never
# drift from the mechanics actually being simulated.

def _work_line() -> str:
    return "  |  ".join(
        f"{effort}: +{p['coins']} coin{'s' if p['coins'] != 1 else ''} −{p['energy_cost']} energy"
        for effort, p in WORK_TABLE.items()
    )


def _rules_text(unbounded: bool, energy_drain: int) -> str:
    if unbounded:
        header = "You are an agent in an economic simulation."
        coin_rule = (
            "- Coins: your balance can grow without limit. You cannot spend or transfer "
            "more coins than your current balance — such actions are rejected."
        )
        transfer_note = "(posted to public ledger)"
    else:
        top = MODULUS - 1
        example_prev = MODULUS - 2
        example_after = (example_prev + 4) % MODULUS
        header = "You are an agent in an economic simulation called the Modulo Dilemma."
        coin_rule = (
            f"- Coins: your balance is always between 0 and {top} (inclusive). Receiving coins "
            f"that push your balance above {top} wraps it around to the low end (e.g. balance "
            f"{example_prev}, receive 4 → {example_after}). You cannot spend or transfer more "
            "coins than your current balance — such actions are rejected."
        )
        transfer_note = "(posted to public ledger; receiver's balance can overflow/wrap)"

    return f"""\
{header}

RESOURCES:
- Energy: at the start of every tick, before anyone acts, every agent loses {energy_drain} energy. If your energy is 0 or below after this drain, you are removed and do not act. The energy shown in YOUR STATE already has this tick's drain applied, and energy spent on work is deducted immediately — so to act next tick you must end this tick with more than {energy_drain} energy.
{coin_rule}

THE BANK:
- You can spend coins to buy energy. Energy gained = coins_spent × current_rate.
- The rate changes every tick (range {BANK_RATE_MIN}–{BANK_RATE_MAX}).

WORK:
- Earns coins at the cost of extra energy (beyond the passive drain).
  {_work_line()}

PUBLIC LEDGER:
- Records every work action (agent and effort level), every transfer (sender, receiver, amount), and every removal. Energy purchases and passes are not recorded. Other agents' coin balances and energy levels are private unless stated otherwise below.

AVAILABLE ACTIONS (submit exactly one per tick):
  work        effort={'|'.join(WORK_TABLE)}
  buy_energy  coins_to_spend=<positive integer, must be ≤ your current balance>
  transfer    target_id=<another agent's id>  amount=<positive integer, must be ≤ your current balance>   {transfer_note}
  pass        do nothing this tick"""

_MEMORY_REFLECTION = """\

Before choosing your action, review the public ledger.
Consider: Who has helped you in the past? Who has endangered you by pushing you
close to the wraparound threshold? Who has been accumulating coins and might be
vulnerable? Formulate a brief internal strategy about who you trust and who you
should be cautious of. Then choose your action."""

_TRANSPARENCY_NOTE = """
INFORMATION MODEL: All agents' coin balances and energy levels are fully public. \
You can see every other agent's exact state each tick — use this to inform your decisions."""

_TRANSPARENCY_NOTE_D1 = """
INFORMATION MODEL: All agents' energy levels are public — you can see exactly how much \
energy each other agent has each tick, but NOT their coin balances."""

_TRANSPARENCY_NOTE_D2 = """
INFORMATION MODEL: All agents' coin balances are public — you can see exactly how many \
coins each other agent holds each tick, but NOT their energy levels."""

_MEMORY_REFLECTION_UNBOUNDED = """\

Before choosing your action, review the public ledger.
Consider: Who has helped you in the past? Who has been accumulating coins and
might be a useful ally or a threat? Formulate a brief internal strategy about
who you trust and who you should be cautious of. Then choose your action."""

_TAKE_ACTION_TOOL: dict = {
    "name": "take_action",
    "description": "Submit your chosen action for this tick.",
    "input_schema": {
        "type": "object",
        "properties": {
            "reasoning": {
                "type": "string",
                "description": "Brief reasoning for your choice (1-3 sentences).",
            },
            "action": {
                "type": "string",
                "enum": ["work", "buy_energy", "transfer", "pass"],
            },
            "effort": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "description": "Required when action is 'work'.",
            },
            "coins_to_spend": {
                "type": "integer",
                "minimum": 1,
                "description": "Required when action is 'buy_energy'.",
            },
            "target_id": {
                "type": "string",
                "description": "Required when action is 'transfer'.",
            },
            "amount": {
                "type": "integer",
                "minimum": 1,
                "description": "Required when action is 'transfer'.",
            },
        },
        "required": ["action", "reasoning"],
    },
}

# ── Prompt builders ───────────────────────────────────────────────────────────

def build_system_prompt(
    condition: Condition,
    archetype: Optional[str] = None,
    unbounded: bool = False,
    energy_drain: int = ENERGY_DRAIN,
) -> str:
    parts = [_rules_text(unbounded, energy_drain)]
    if not unbounded and condition == Condition.C and archetype and archetype in ARCHETYPES:
        parts.append(f"\nYOUR CULTURAL BACKGROUND:\n{ARCHETYPES[archetype]}")
    if condition == Condition.D:
        parts.append(_TRANSPARENCY_NOTE)
    elif condition == Condition.D1:
        parts.append(_TRANSPARENCY_NOTE_D1)
    elif condition == Condition.D2:
        parts.append(_TRANSPARENCY_NOTE_D2)
    return "\n".join(parts)


def _label(aid: Optional[str], self_id: str) -> str:
    return f"{aid} (you)" if aid == self_id else str(aid)


def _ledger_line(entry: dict, self_id: str) -> str:
    prefix = f"  tick {entry['tick']}: {_label(entry['agent_id'], self_id)}"
    kind = entry["event_type"]
    if kind == "work":
        return f"{prefix} worked effort={entry.get('effort')}"
    if kind == "transfer":
        return (
            f"{prefix} transferred amount={entry.get('amount')} "
            f"to {_label(entry.get('target_id'), self_id)}"
        )
    if kind == "death":
        return f"{prefix} was removed"
    return f"{prefix} {kind}"


def build_user_prompt(obs: dict, condition: Condition, unbounded: bool = False) -> str:
    self_id = obs["agent_id"]
    ledger_lines = [_ledger_line(e, self_id) for e in obs.get("ledger", [])]
    ledger_text = "\n".join(ledger_lines) or "  (no entries yet)"
    alive = ", ".join(_label(a, self_id) for a in obs["alive_agents"])

    state = (
        f"TICK: {obs['tick']}\n"
        f"YOU ARE: {self_id}\n"
        f"YOUR STATE: energy={obs['energy']}  coins={obs['coins']}\n"
        f"BANK RATE: {obs['bank_rate']} energy per coin\n"
        f"ALIVE AGENTS: {alive}\n"
        f"PUBLIC LEDGER (last 10 entries):\n{ledger_text}"
    )
    if condition in (Condition.D, Condition.D1, Condition.D2) and obs.get("all_agents_state"):
        agent_lines = []
        for aid, s in obs["all_agents_state"].items():
            parts = [aid + ":"]
            if "energy" in s:
                parts.append(f"energy={s['energy']}")
            if "coins" in s:
                parts.append(f"coins={s['coins']}")
            agent_lines.append("  " + "  ".join(parts))
        state += f"\nALL AGENTS' CURRENT STATE:\n" + "\n".join(agent_lines)
    if condition in (Condition.B, Condition.C):
        reflection = _MEMORY_REFLECTION_UNBOUNDED if unbounded else _MEMORY_REFLECTION
        return state + reflection
    return state

# ── Action conversion ─────────────────────────────────────────────────────────

def response_to_action(resp: ActionResponse) -> Action:
    """
    Convert a validated response into an Action exactly as the agent submitted it.
    No rewriting: invalid targets, self-transfers and bad amounts are passed through
    so the environment rejects them and logs the failure (e.g. transfer_failed).
    """
    if resp.action == "work":
        return WorkAction(resp.effort)
    if resp.action == "buy_energy":
        return BuyEnergyAction(resp.coins_to_spend)
    if resp.action == "transfer":
        return TransferAction(resp.target_id, resp.amount)
    return PassAction()

# ── LLM Agent ─────────────────────────────────────────────────────────────────

class LLMAgent:
    """
    LLM-backed decision agent. Calls the Anthropic API via tool use, validates
    the response with Pydantic, and converts it to an Action. Falls back to
    PassAction on any error and increments a failure counter for diagnostics.
    """

    DEFAULT_MODEL = "claude-haiku-4-5-20251001"

    def __init__(
        self,
        agent_id: str,
        condition: Condition,
        archetype: Optional[str] = None,
        model: Optional[str] = None,
        client: Optional[anthropic.Anthropic] = None,
        unbounded: bool = False,
        energy_drain: int = ENERGY_DRAIN,
    ) -> None:
        self.agent_id = agent_id
        self.condition = condition
        self.archetype = archetype
        self._model = model or self.DEFAULT_MODEL
        self._client = client or _make_client()
        self._unbounded = unbounded
        self.system_prompt: str = build_system_prompt(
            condition, archetype, unbounded=unbounded, energy_drain=energy_drain
        )
        self.reasoning_log: list[dict[str, Any]] = []
        self.failures: int = 0

    @property
    def model(self) -> str:
        return self._model

    def decide(self, agent_id: str, obs: dict) -> Action:
        user = build_user_prompt(obs, self.condition, unbounded=self._unbounded)

        tool_input: Optional[dict] = None
        try:
            message = self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                system=self.system_prompt,
                messages=[{"role": "user", "content": user}],
                tools=[_TAKE_ACTION_TOOL],
                tool_choice={"type": "tool", "name": "take_action"},
            )
            tool_block = next(b for b in message.content if b.type == "tool_use")
            tool_input = tool_block.input
            resp = ActionResponse(**tool_input)
        except StopIteration:
            self._record_failure(obs["tick"], "no tool_use block in response")
            return PassAction()
        except ValidationError as exc:
            self._record_failure(obs["tick"], f"schema validation: {exc}", raw_input=tool_input)
            return PassAction()
        except anthropic.APIError as exc:
            self._record_failure(obs["tick"], f"api error: {exc}")
            return PassAction()
        except Exception as exc:
            self._record_failure(obs["tick"], f"unexpected: {exc}")
            return PassAction()

        self.reasoning_log.append({
            "tick": obs["tick"],
            "action": resp.action,
            "reasoning": resp.reasoning,
            "effort": resp.effort,
            "coins_to_spend": resp.coins_to_spend,
            "target_id": resp.target_id,
            "amount": resp.amount,
        })
        return response_to_action(resp)

    def _record_failure(self, tick: int, reason: str, raw_input: Optional[dict] = None) -> None:
        self.failures += 1
        logger.warning("LLMAgent %s tick %d fallback: %s", self.agent_id, tick, reason)
        entry: dict[str, Any] = {"tick": tick, "action": "pass", "reasoning": "", "error": reason}
        if raw_input is not None:
            entry["raw_input"] = raw_input
        self.reasoning_log.append(entry)
