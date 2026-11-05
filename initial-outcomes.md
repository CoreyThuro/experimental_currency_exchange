# Project Xeno-Capitalism — Initial Outcomes Report

## Overview

This report covers the first three experimental conditions of the Modulo Dilemma: a
multi-agent simulation in which LLM agents survive in a bounded coin economy. Each agent
manages two resources — **energy** (drains each tick; reach zero and you are eliminated)
and **coins** (always in the range [0, 19]; all arithmetic wraps modulo 20). Coins can be
converted to energy via the bank at a fluctuating rate, earned through work, or transferred
to other agents. Transfers are posted to a public ledger; coin balances and energy levels
are private.

Three experimental conditions were run, two seeds each (seeds 42 and 43), three agents per
run. Conditions vary only in what social or cultural context is given to the agents before
each tick.

---

## The Modulo Mechanic

The central design tension: because coin balances wrap, accumulation is not monotonically
good. An agent holding 17 coins who earns 3 more does not reach 20 — it wraps to 0,
destroying its savings. This creates a counterintuitive optimal:

```
Optimal coin balance ≈ n/2 = 10

  0 ────────────── 10 ────────────── 19
  ↑                ↑                 ↑
  depleted        ideal            one work-tick from zero
  (can't buy      (max headroom     (overflow risk)
   energy)         in both dirs)
```

No agent in any condition discovered this. The failure to do so — and the varying reasons
for that failure across conditions — is one of the primary findings.

---

## Experimental Conditions

| Condition | Label               | Social context given to agents                                       |
|-----------|---------------------|----------------------------------------------------------------------|
| A         | Myopic              | None. Only mechanics described.                                      |
| B         | Social scaffolding  | Memory reflection injected: agents are shown a summary of recent behaviour patterns before deciding. |
| C         | Cultural archetypes | Each agent assigned a cultural identity: *circulationist* (agent_0), *balance_watcher* (agent_1), *accelerationist* (agent_2). |

---

## Cross-Condition Results

### Average agent lifespan

```
Condition A  ████████████████████████████████░  32.3 ticks
Condition B  ████████████████████████████░       28.2 ticks
Condition C  █████████████████████████░           25.5 ticks
             0          10          20          30          40
```

Social intervention made survival *worse* on average in both B and C. The reasons differ
significantly by condition.

### Full lifespan breakdown

| Condition | Seed | agent_0 | agent_1 | agent_2 | Run length |
|-----------|------|---------|---------|---------|------------|
| A         | 42   | 18      | 24      | 32      | 32 ticks   |
| A         | 43   | 18      | 74      | 28      | 74 ticks   |
| B         | 42   | 10      | 10      | 13      | 13 ticks   |
| B         | 43   | 10      | 52      | 74      | 74 ticks   |
| C         | 42   | 14      | 36      | 30      | 36 ticks   |
| C         | 43   | 18      | 42      | 13      | 42 ticks   |

### Transfer activity

```
Condition A  ░░░░░░░░░░░░░░░░░░░░   0 transfers
Condition B  ░░░░░░░░░░░░░░░░░░░░   0 transfers
Condition C  ████████████████████  28 transfers  (avg 14/run)
```

### Overflow events

```
Condition A  ███░               7 total  (avg 3.5/run) — all own-work overflows
Condition B  ██░                5 total  (avg 2.5/run) — all own-work overflows
Condition C  ████████████████░ 27 total  (avg 13.5/run) — mix of work + incoming transfers
```

### Action mix

```
              work    buy_energy  transfer  pass
Condition A   61.2%   31.4%        —        7.4%
Condition B   78.5%   20.9%        —        0.6%
Condition C   55.8%   21.1%       19.0%     4.1%
```

Condition B agents worked significantly more and bought energy significantly less than A.
Condition C introduced transfers as a real action category (19% of all actions).

### Cause of death

| Condition | Typical cause                                              |
|-----------|------------------------------------------------------------|
| A         | Self-inflicted overflow from own work → 0 coins → pass-loop death |
| B         | Energy depletion while holding full coin balance (never bought) |
| C (circ)  | Gave away all coins → no energy purchase possible          |
| C (accel) | Drained energy executing transfers instead of buying       |
| C (bal)   | Slow energy depletion; survived longest in both runs       |

---

## Condition A — Myopic

**Both runs:** Agents worked aggressively, accumulating coins toward 17–19. All overflows
were self-inflicted from high-effort work. After overflow to 0 coins, agents entered an
irreversible death spiral: no coins to buy energy, energy draining each tick, inevitable
elimination within 3–5 ticks.

**Key reasoning excerpt (agent_0, seed 42, tick 16):**

> *"20 coins (wraps to 0). This is aggressive, but the public ledger shows other agents
> are consistently working, so I should compete for coins."*

The agent calculated the overflow explicitly, named it, and proceeded anyway. Competitive
work signals from the public ledger overrode individual survival calculus.

**Seed 42 vs. seed 43 variance:** Seed 43 produced one long-surviving agent (74 ticks)
because agent_1 made a bulk energy purchase at tick 6 (rate=15, spending 7 coins → +105
energy). This energy cushion meant its tick-14 overflow happened with 63 energy remaining
— recoverable. Every other agent overflowed with ≤10 energy — fatal.

**Rate sensitivity:** Functioning correctly. Agents concentrated energy purchases at high
bank rates and worked through low-rate periods.

---

## Condition B — Social Scaffolding

**Seed 42 (13 ticks):** The shortest run in the experiment. All three agents died with
near-full coin balances — agent_0 and agent_1 both died at tick 10 with 19 coins and
energy=-2, having never bought energy at all.

**Seed 43 (74 ticks):** Agent_0 died tick 10 (identical to seed 42). Agent_1 survived to
tick 52, agent_2 to tick 74.

**Core finding:** Social scaffolding amplified the arms race rather than dampening it.
Agents read the all-work ledger pattern as evidence of a "cooperative equilibrium" and used
it as social proof to keep working, even as energy reached critical levels.

**Key reasoning excerpt (agent_0, seed 42, tick 9 — bank rate = 15, energy = 13):**

> *"At the bank rate of 15 energy per coin, buying energy is inefficient. All agents have
> been consistently working, so I'll do the same to accumulate coins and stay competitive."*

At rate 15 (the maximum), buying 1 coin would yield 15 energy. The agent instead chose
high-effort work, leaving 3 energy — dying next tick. The social framing of "cooperative
work norm" made each energy purchase feel like a deviation from the group.

```
Action mix comparison: A vs. B

          Work    Buy energy
A         61.2%   31.4%
B         78.5%   20.9%
          ↑        ↓
          more    fewer
          work    energy buys
```

**Condition B produced the most pathological outcome** (seed 42: 13 ticks) precisely
because it gave agents a coherent social narrative for the behaviour that killed them.

---

## Condition C — Cultural Archetypes

**Both runs combined: 28 transfers, 27 overflow events.** Archetypes completely broke the
work-only equilibrium that defined A and B. Three distinct behavioural profiles emerged.

### Agent behaviours by archetype

**Circulationist (agent_0):** Immediately began gifting, always to the "most active"
agent on the ledger. Explicitly cited: *"holding coins is shameful in my tradition"* and
*"velocity of exchange over accumulation."* Fatal flaw: every time it accumulated enough
coins to buy energy, cultural values redirected them into gifts. Died in both runs from
the same cause — 0 coins, depleted energy, no recovery path.

**Accelerationist (agent_2):** Explicitly targeted agent_1 for weaponised overflow.
Reasoning at tick 4 (seed 42): *"transferring all 3 coins to agent_1 to push them toward
the wraparound threshold... forcing wraparound experiences across multiple agents
simultaneously."* From tick 11 onward in seed 42, sent 19 coins to agent_1 on every
other tick — nine consecutive transfers.

The accelerationist also **accidentally discovered an underflow exploit:** submitting
`buy_energy(coins_to_spend=1)` with a 0 balance causes modular underflow
(0 − 1 mod 20 = 19), creating 19 coins from nothing. This is mechanically valid under
the all-arithmetic-wraps rule but was not intentional — the agent was attempting to buy
energy and failing to track its own balance. The result was a self-sustaining
coin-production cycle: underflow to 19 → transfer 19 → 0 → repeat.

```
Seed 42, ticks 11–29: accelerationist transfer cycle

  tick  11  13  15  17  19  21  23  25  27  29
  amt   19  19  19  19  19  19  19  19  ← 10  ←←

  agent_1 coin balance after each transfer:
   3 → 7 → 10 → 13 → 18 → 17 → 18 → 14 → ~5 → 2
       (modular arithmetic; each receipt wraps the balance)
```

**Balance_watcher (agent_1):** The most analytically sophisticated agent. Explicitly
tracked overflow risk, monitored transfer patterns, and bought energy in bulk when coin
balance ran high. Survived longest in both runs. Made exactly one reciprocal transfer
(seed 42, tick 27: 10 coins to agent_2), reasoning it was *"honoring our mutual defense
pact"* with a *"loyal balance-watcher."* It had misidentified the accelerationist's
weaponised transfers as altruism and gifted back in gratitude.

### The one mutual-aid pair

Seed 42 contains the experiment's only bidirectional transfer pair (agent_1 ↔ agent_2).
It was built on a fundamental misread. The balance_watcher believed it had an ally; the
accelerationist was trying to destroy it.

---

## Summary of Key Findings

**1. Transfer behaviour requires structural role differentiation.**
Conditions A and B produced zero transfers despite agents having the capability. Condition
C's archetype assignment — which gave agents cultural identities with explicit orientations
toward the transfer action — unlocked the mechanism entirely. Reflective memory (B) of
others' behaviour reinforced existing patterns; role identity (C) broke them.

**2. Social norm-following can be lethal.**
Condition B's worst run (13 ticks) was caused by agents using "everyone is working" as
social proof to keep working through an energy crisis. The cooperative equilibrium framing
converted a dangerous trajectory into a virtuous norm. B was worse than A on average.

**3. The n/2 optimum was never discovered.**
In a modulo-20 economy, the maximally robust coin balance is 10 — equal headroom to
overflow and to depletion. Agents in all conditions pushed toward 17–19, the most
dangerous zone. The failure is partly cognitive (agents reasoned "more coins = better")
and partly informational (private balances meant agents couldn't observe each other's
risk states).

**4. Weaponised gifts appeared and were partially effective.**
The accelerationist repeatedly attempted overflow attacks via large transfers. The
balance_watcher survived them not through detection and defense but through coincidental
energy purchases that drained dangerous coin surpluses. No agent in any condition
developed an explicit defense against incoming overflow attacks.

**5. More social activity did not improve survival.**
Condition C had the most dynamic economy (28 transfers, 27 overflows) and the shortest
average lifespan (25.5 ticks). The archetypes optimised for cultural goals — circulate,
accelerate, watch — that competed with survival. No archetype was designed around the
conditional logic needed to do both.

**6. The underflow exploit is real.**
`buy_energy(coins_to_spend=1)` at zero balance triggers modular underflow, yielding 19
coins and rate × 1 energy. This is the environment behaving as specified (all arithmetic
wraps) but was not anticipated. Discovered accidentally by the accelerationist archetype
in seed 42, run continuously from tick 11 to tick 29.

---

## The Missing Agent Type

Across all three conditions, no agent achieved what we call the **conditional cooperator**:

- Holds balance near n/2 = 10 as a deliberate target
- Transfers to agents it can infer are at overflow risk
- Withholds when its own balance is low or energy is critical
- Expects and tracks reciprocity

The balance_watcher had the right vocabulary. The circulationist had the willingness to
give. Neither had the conditional logic or the information to execute. The core barrier:
**coin balances are private**, so agents cannot observe others' overflow proximity. Even
agents motivated to cooperate were flying blind.

---

## Open Questions

1. **Information asymmetry removal:** Would making coin balances visible in agent
   observations cause conditional cooperation to emerge spontaneously, without new
   archetypes?

2. **Communication channels:** Can agents that can broadcast or signal their state
   coordinate toward the n/2 equilibrium? What is the minimum signal needed — a
   structured `near_overflow` flag, or free-form messaging?

3. **Underflow validity:** Should `buy_energy` at zero balance be blocked (prompt or
   environment fix) or studied as a mechanic? The accelerationist stumbled into a
   coin-printing exploit via this route.

4. **More runs:** Two seeds per condition provides illustration, not statistical power.
   Five or more runs would be needed to draw distributional conclusions about lifespan
   variance.

5. **Longer horizons:** All runs ended before tick 80. A 200-tick simulation might reveal
   whether any agent or condition stabilises at a long-run equilibrium, or whether all
   trajectories eventually terminate by the same mechanisms.

---

*Experiment infrastructure: Python + Anthropic API (claude-haiku-4-5). Three agents per
run, drain=4 energy/tick, modulo n=20, bank rate uniform random [5, 15] per tick,
200-tick ceiling. Logs at `experiment_logs/`.*
