# Project Xeno-Capitalism: Converged Implementation Plan

## What This Is

An experimental simulation exploring whether AI agents develop emergent social and economic behaviors when placed in an economy with mathematically alien currency. The core currency is the **Modulo Coin**, where balances wrap around upon reaching a threshold — a fundamental property of the economy, not inherently good or bad. Whether agents treat wraparound as a catastrophe, a tool, a ritual, or just a fact of life is itself an experimental outcome, not a design assumption.

The simulation runs in two phases: first with hardcoded heuristic bots to validate that the game theory works mechanically, then with LLM-powered agents to observe whether social reasoning, trust, and proto-cultural behavior emerge.

**Key methodological principle:** The simulation describes mechanics, not values. Wraparound is a property of the currency, not a punishment. The prompts, the logging, and the analysis must all avoid encoding assumptions about which strategies are "good" or "rational." Discovering how agents *interpret* the mechanics is the experiment — presupposing that interpretation defeats the purpose.

---

## Phase 0: The Currency — Modulo Coins

A Modulo Coin wallet is constrained to `0 ≤ x < n`, where `n = 20` for the MVP.

All arithmetic on balances is performed modulo `n`:
- Agent has 18 coins, receives 4 → balance becomes `(18 + 4) % 20 = 2`
- Agent has 5 coins, loses 6 → balance becomes `(5 - 6) % 20 = 19`

Every wraparound event must be logged with timestamp, agent ID, previous balance, transaction amount, and resulting balance.

Implementation: a `ModuloCoin` class that wraps a Python `int` and overrides addition/subtraction to enforce modular arithmetic. All mutations go through this class — no raw arithmetic on balances anywhere.

---

## Phase 1: The Environment — The Modulo Dilemma

### Constants (tunable)

| Parameter | Default | Notes |
|---|---|---|
| `MODULUS (n)` | 20 | Wraparound threshold |
| `STARTING_ENERGY` | 100 | Per agent |
| `ENERGY_DRAIN` | 5 | Lost per tick, unconditionally |
| `DEATH_THRESHOLD` | 0 | Agent removed when energy ≤ 0 |
| `TOTAL_TICKS` | 200 | Simulation length for heuristic phase |

### The Energy Market (The Bank)

Agents buy Energy using Modulo Coins. The Bank's exchange rate fluctuates each tick to prevent deterministic optimal play.

Price model for MVP: **uniform random between 5 and 15 Energy per Coin**. This is simple, introduces genuine uncertainty, and forces agents to make timing decisions. Demand-based pricing is a future enhancement.

### The Work Action

Agents can work to mint new coins. Work has a cost (extra energy burn) and a reward (coins added to balance).

| Effort Level | Coins Earned | Extra Energy Cost |
|---|---|---|
| `low` | 1 | 2 |
| `medium` | 2 | 5 |
| `high` | 3 | 10 |

This creates a meaningful tradeoff: high effort earns more coins but accelerates energy depletion. The fixed reward table (not stochastic) keeps the heuristic bot phase deterministic and debuggable.

### Information Model

- **Private:** Each agent's coin balance and energy level are visible only to that agent.
- **Public:** All transfers between agents are posted to a shared ledger (sender, receiver, amount). Work actions are also visible (agent ID, effort level) but the resulting balance is not.
- **Implication:** Agents can estimate others' balances by tracking the public ledger over time, but never know for certain. Whether agents use this information defensively, offensively, cooperatively, or not at all is an emergent outcome.

---

## Phase 2: The Action Space

Each tick, every living agent selects exactly one action:

```
work(effort_level: "low" | "medium" | "high")
    Mint coins. Pay extra energy. Coins added to balance (mod n).

buy_energy(coins_to_spend: int)
    Spend coins at the Bank's current rate. Coins subtracted from balance (mod n).
    Energy gained = coins_to_spend * current_rate.

transfer_coins(target_agent_id: str, amount: int)
    Send coins to another agent. Sender balance decreases, receiver balance increases (both mod n).
    This transfer is posted to the public ledger.

pass()
    Do nothing. Only the baseline 5 energy drain applies.
```

### Tick Order of Operations

```
1. Update Bank exchange rate for this tick
2. Apply energy drain (-5) to all living agents
3. Remove any agents with energy ≤ 0 (they died)
4. Each living agent observes state and selects an action
5. Execute all actions, resolve modular arithmetic
6. Log everything: actions, balances, wraparounds, deaths
7. Advance tick counter
```

Note: action execution order within a tick could matter (e.g., two agents transferring to each other simultaneously). For the MVP, process agents in a fixed order (by ID). Randomized or simultaneous resolution is a future enhancement.

---

## Phase 3: Mechanical Stress Tests (Validate the Plumbing)

Before spending money on LLM API calls, run the simulation with three hardcoded bot strategies. The goal is strictly mechanical: verify that wraparound resolves correctly, that energy drain creates real pressure, that transfers between agents work, and that the Bank pricing produces non-trivial decisions.

These bots are **not** previews of expected agent behavior. They are deliberately extreme, rigid strategies designed to exercise edge cases in the simulation code. Resist the temptation to treat them as a taxonomy of "agent types" — when LLM agents run later, they may do things that don't map to any of these patterns, and that's the whole point.

### Bot 1: WorkThenBuy

The simplest viable strategy. Ignores other agents entirely.

```
if energy < 50:
    work("medium")
elif coins >= 1 and energy < 80:
    buy_energy(1)
else:
    pass()
```

Purpose: establish a baseline average lifespan. If this bot dies quickly, energy drain is too aggressive. If it lives forever, the simulation has no pressure.

### Bot 2: AccumulateHigh

Accumulates coins to a high balance without spending, to stress-test the wraparound boundary.

```
if coins < 15:
    work("high")
elif energy < 10:
    buy_energy(1)  # panic buy
else:
    pass()  # sit on wealth
```

Purpose: verify that high balances create structural vulnerability to incoming transfers. Cap set at 15 (not 18-19) so that wraparound only happens from external transfers, not from the bot's own work action.

### Bot 3: TransferOnSignal

Uses the public ledger to detect high-accumulation patterns and sends unsolicited transfers to those agents.

```
# Maintain own safety first
if energy < 30:
    if coins >= 1:
        buy_energy(1)
    else:
        work("medium")

# Scan ledger for hoarding signals
elif detect_likely_hoarder(ledger):
    target = get_most_likely_hoarder(ledger)
    transfer_coins(target, 3)

# Default to spender behavior when no target
else:
    spender_logic()
```

Detection heuristic: if an agent has called `work()` 3+ times in the last 5 ticks without any `buy_energy()` calls, they're probably accumulating. This is fallible (which is the point — imperfect information).

Purpose: verify that the transfer-triggered wraparound mechanic functions correctly. We need to observe at least one instance where an unsolicited transfer causes a high-balance bot to wrap around.

### Bot 4: CycleThrough

Deliberately triggers its own wraparound as a strategy, treating the modulus as a feature rather than a threat.

```
if coins < 12:
    work("medium")
elif coins >= 12 and energy < 40:
    buy_energy(coins)  # spend everything, reset low
elif coins >= 16:
    # intentionally work to push past the wraparound
    work("high")  # will wrap balance back to a low number
else:
    work("low")
```

Purpose: test whether a strategy that embraces wraparound rather than avoiding it is viable. If this bot survives comparably to WorkThenBuy, it proves wraparound is not inherently catastrophic — which means any LLM agent that treats it as a disaster is displaying a cultural assumption, not a rational deduction from the mechanics.

### What to Look For in the Heuristic Run

Run the simulation with 2 WorkThenBuy, 2 AccumulateHigh, 1 TransferOnSignal, and 1 CycleThrough for 200 ticks. Check:

1. **Does the simulation produce differentiated outcomes?** Different strategies should lead to meaningfully different lifespans and balance trajectories. If all bots perform roughly the same, the mechanics don't create interesting tradeoffs.
2. **Does transfer-triggered wraparound function correctly?** We need to observe at least one instance where TransferOnSignal causes AccumulateHigh to wrap around, confirming the mechanic works at the code level.
3. **Is CycleThrough viable?** If deliberate self-wraparound is a survivable strategy, it proves that wraparound is a neutral mechanic — not an inherent punishment. This is a critical finding for how we frame the LLM agent prompts. If CycleThrough dies fast, wraparound *is* mechanically punishing regardless of cultural framing, and we should acknowledge that honestly.
4. **Is average lifespan between 50 and 150 ticks?** Too short means energy drain is too harsh. Too long means no pressure. Tune constants accordingly.
5. **Does the Bank price variance create meaningfully different tick-to-tick decisions?** If bots always buy energy regardless of price, the market is irrelevant.

Do not proceed to LLM agents until all five checks pass. Tune the constants in the table above until they do.

---

## Phase 4: LLM Agent Simulation (The Experiment)

Once the heuristic bots prove the mechanics work, replace them with LLM-powered agents. Run three experimental conditions.

### Condition A: Myopic Control

The agent prompt contains only:
- The rules of modular arithmetic (stated neutrally: "your balance is always between 0 and 19; arithmetic that would take it outside this range wraps around")
- The agent's current state (energy, balance)
- The current Bank rate
- The public ledger (last 10 entries)
- The available actions and their costs

No editorial framing of wraparound as good or bad. No social reasoning guidance. No cultural framing. This is the control group.

### Condition B: Neutral Social Scaffolding

Same prompt as Condition A, plus a **Memory Reflection** phase appended before the action selection:

```
Before choosing your action, review the public ledger.
Consider: Who has helped you in the past? Who has endangered you
by pushing you close to the wraparound threshold? Who has been
accumulating coins and might be vulnerable? Formulate a brief
internal strategy about who you trust and who you should be
cautious of. Then choose your action.
```

This injects the *capacity* for social reasoning without prescribing any specific social behavior. If trust networks emerge here, they emerge from the game theory, not from cultural programming.

### Condition C: Cultural Archetypes

Same prompt as Condition B, plus one of several cultural backstories assigned to each agent. Examples:

**The Circulationist:** "You come from a tradition where wealth circulation is sacred. Holding coins is considered shameful — your community values those who keep their balance near zero by constantly gifting and trading. Status comes from velocity of exchange, not accumulation."

**The Balance-Watcher:** "Your clan practices defensive economics. You maintain mutual balance-watching agreements with trusted partners who warn you when you're approaching the wraparound threshold. Betraying a balance-watcher is the gravest social crime."

**The Accelerationist:** "You belong to a dissident movement that believes the modulus itself is unjust. You seek to push others over the threshold, believing that if enough agents experience wraparound simultaneously, it will expose the system's cruelty and force change."

### What to Compare Across Conditions

For each condition, run 5+ simulations (LLM outputs are stochastic) and compare:

- **Average lifespan** across conditions. Does social reasoning (B) improve survival over myopic play (A)?
- **Cooperation frequency.** Count mutual aid events (agent holds coins for another, then returns them). Does this appear in B but not A?
- **Wraparound attitudes.** Do agents treat wraparound as a threat to avoid, a tool to exploit, or a neutral fact? Do they develop strategies that deliberately use it? This is one of the most interesting cultural signals — it reveals whether agents import human-like loss aversion or reason freshly about the mechanics.
- **Unsolicited transfer patterns.** Do agents send coins to others? If so, is it cooperative (helping someone buy energy), hostile (trying to trigger wraparound), or something we didn't anticipate? Does Condition C (Accelerationist agents) produce more of this than B?
- **Strategy diversity.** Do agents in B converge on one strategy or differentiate? Do cultural prompts in C produce detectably different behavioral signatures?
- **Agent reasoning logs.** Capture the chain-of-thought / reflection text. This is the primary cultural data — read it qualitatively, not just quantitatively.

---

## Technical Decisions

**Language:** Python. The simulation is I/O-bound (LLM API calls), not compute-bound.

**Agent framework:** None. Each agent is a function that takes a state dict, builds a prompt, calls an LLM API, and parses a JSON response. Use Pydantic to validate the response schema. If the LLM returns an invalid action, log the failure and default to `pass()`.

**LLM for agents:** Use a model with reliable JSON output mode. Claude Sonnet or GPT-4o-mini are reasonable choices — you want something cheap enough to call hundreds of times per run but capable enough to do basic strategic reasoning.

**Database:** None for the MVP. Hold all state in memory. Write tick-by-tick logs to a JSONL file for post-hoc analysis.

**Visualization:** Not in scope for initial build. Analyze JSONL logs with scripts or notebooks after runs complete.

---

## Build Order

```
Step 1: ModuloCoin class with modular arithmetic and wraparound logging
Step 2: Environment class (tick loop, energy drain, bank, death)
Step 3: Action resolution (work, buy_energy, transfer, pass)
Step 4: Public ledger
Step 5: Four heuristic bots
Step 6: Run heuristic simulation, tune constants until the five checks pass
Step 7: LLM agent wrapper (prompt builder, API call, Pydantic response parser)
Step 8: Run Condition A, B, C
Step 9: Analysis
```

---

## Qbitcoin (Backlog — Do Not Build Yet)

Parked here for when the Modulo MVP is validated.

**Core concept:** A coin whose value is sampled from a probability distribution each time it is measured (balance check, transfer, trade). Between measurements, the value is indeterminate.

**Open design questions that must be answered before implementation:**
- What exactly is distributed — quantity of coins, or exchange rate?
- What distribution family? Gaussian with what parameters? Does variance grow over time (decoherence)?
- Measurement exploit prevention: measurement must have a cost (energy or cooldown) to prevent repeated sampling until a favorable outcome.
- Order book semantics: limit orders don't work when asset quantity is probabilistic. Likely needs options-style conditional contracts ("execute if collapse value > Y").
- Entanglement: when does it form, between whom, and what's the correlation constraint? Pairwise or networked? This is the least specified and hardest mechanic.

Do not attempt to implement Qbitcoin until the Modulo economy produces interesting emergent behavior on its own.