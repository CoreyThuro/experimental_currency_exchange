# What's Next — Modulo Dilemma

*Status as of Phase 3 complete. Conditions A/B/C run with 2 seeds each.*

> **Note on ENERGY_DRAIN:** The heuristic bots pass their 5 validation checks at `ENERGY_DRAIN=2` (auto-tuned by `run_heuristic.py`). The LLM experiment uses the module-level default `ENERGY_DRAIN=5` in `environment.py`. These are different numbers for different purposes — the heuristic tuning is not a change to the LLM experiment's drain rate.

---

## Current State

| Phase | Description | Status |
|-------|-------------|--------|
| 0 | ModuloCoin class | ✓ Done |
| 1 | Environment (tick loop, bank, death) | ✓ Done |
| 2 | Action space (work, buy, transfer, pass) | ✓ Done |
| 3 | Heuristic bots — 5/5 validation checks pass | ✓ Done |
| 4 | Capitalism baseline | **Not started** |
| 5 | LLM conditions A/B/C | Partial (2 seeds each; need 5+) |
| 6 | Progressive infrastructure (D/E/F) | Not started |

Two bugs were fixed before the last session ended:

- `buy_energy` with more coins than held now returns `buy_energy_failed(insufficient_coins)` instead of modular underflow
- `transfer` with more coins than held now returns `transfer_failed(insufficient_coins)` instead of modular underflow

These affect any re-analysis of Condition C data: the accelerationist's "coin-printing" cycle (ticks 11–29 of seed 42) relied on the underflow exploit and would not occur under the current code.

The agent prompt in `llm_agent.py` was also updated to match: the old text told agents that overspending wraps by underflow (the spend-6-with-5-coins example). That example has been removed and the rules now state that overspending is rejected. **Before re-running any LLM conditions, verify the prompt matches the environment rules.**

---

## Step 1 — Capitalism Baseline (Phase 4)

**This is the most important missing piece.** Without it the research question cannot be answered.

The research question: *does a modulo economy sustain its population as well as or better than conventional capitalism?*

### What to build

Three separate changes are required, not just a flag:

**1. Environment mechanics** — Add an `unbounded: bool = False` parameter to `Environment.__init__`. When `True`, skip the `% MODULUS` in `ModuloCoin.add()` and `ModuloCoin.subtract()` so balances grow without limit. Also drop the `insufficient_coins` guard in `_execute_action` for unbounded mode — agents should be able to spend freely. Everything else stays identical: same tick loop, same bank rate, same energy drain, same starting energy.

**2. Agent prompt** — The current `_RULES` in `llm_agent.py` describes modulo mechanics (wraparound, balance range 0–19). These must not appear in the capitalism baseline prompt. Create a separate `_RULES_UNBOUNDED` variant that describes standard arithmetic (balances can grow without limit; no wraparound; overspending is still rejected). Pass the correct rules based on a new `unbounded` parameter in `build_system_prompt()`.

**3. Condition C archetypes** — The three archetypes in `ARCHETYPES` are defined entirely in terms of modular mechanics (wraparound threshold, the modulus being "unjust", etc.). For the capitalism baseline they are meaningless or contradictory. Either define capitalism-mode archetype variants, or run the capitalism baseline under Conditions A and B only and skip C.

### What to measure

Run the capitalism baseline with all three LLM prompt conditions (A, B, C) over 5+ seeds each. For every run, track the three metrics defined in [plan.md](plan.md):

1. **Population survival curve** — % of agents alive at tick 50, 100, 150, 200
2. **Gini coefficient of energy** — inequality in the survival resource over time
3. **Minimum lifespan** — tick at which the first agent dies (the floor, not the average)

### What not to assume

Capitalism might not produce Pareto hoarding. If LLM agents prompted to survive (not to accumulate) all behave similarly under unbounded currency, that is itself a finding: extreme inequality is an agent-goal phenomenon, not a currency-mechanics one.

---

## Step 2 — More LLM Seeds (Phase 5 completion)

The current A/B/C data (2 seeds each) is illustrative, not statistical. The plan requires 5+ seeds per condition before drawing distributional conclusions.

The existing logs cover seeds 42 and 43 (2 runs per condition). Log files are opened in write mode, so running `--runs 5` from the default base seed would **overwrite** seeds 42 and 43. To add 3 more seeds safely:

```
python -m modulo_dilemma.run_experiment --condition A --runs 3 --seed 44
python -m modulo_dilemma.run_experiment --condition B --runs 3 --seed 44
python -m modulo_dilemma.run_experiment --condition C --runs 3 --seed 44
```

This produces seeds 44, 45, 46 and leaves the existing seed-42/43 logs intact.

Run the same 5 seeds per condition on the capitalism baseline once Step 1 is built.

---

## Step 3 — Comparative Analysis (Phase 5 conclusion)

Once Step 1 and Step 2 are done, compute and compare across all conditions × both currency modes:

| Metric | Modulo A | Modulo B | Modulo C | Cap A | Cap B | Cap C |
|--------|----------|----------|----------|-------|-------|-------|
| Avg lifespan | | | | | | |
| Survival at tick 100 | | | | | | |
| Gini (energy, tick 50) | | | | | | |
| Minimum lifespan | | | | | | |
| Transfer rate | | | | | | |

The comparison drives the Phase 6 decision tree.

---

## Step 4 — Progressive Infrastructure (Phase 6), if needed

These are contingent on Step 3 results. Run them in order; each one answers "how much institutional help does the modulo economy need?"

### Condition D — Public balances

Change `get_observation()` to include all agents' coin and energy levels. No new actions. No new mechanics.

*If D produces sustainable collective survival: the failure in A–C was an information problem, not structural. The currency works; agents just couldn't see well enough to cooperate.*

### Condition E — Broadcast messages

Revert to private balances. Add a new action:

```
broadcast_status(message: str)  # max 10 words, costs 1 energy
```

Message is appended to the public ledger. Agents can ask for help, warn others, lie, or negotiate.

Log every message verbatim — these are the primary cultural data.

*If E produces coordination without perfect information: language is sufficient for this economy.*

### Condition F — Communal vault

If E still produces mass die-offs, add a shared vault:

```
deposit_to_vault(amount: int)    # personal wallet → vault (no modulus cap on vault)
withdraw_from_vault(amount: int) # vault → personal wallet (subject to agent's modulus)
```

Vault balance is public. Tests whether agents invent a functional commons (safety net) or free-ride.

---

## Open Questions Carried Forward

From [initial-outcomes.md](initial-outcomes.md):

1. **Information asymmetry removal (→ Condition D):** Would visible balances allow conditional cooperation to emerge without new archetypes?
2. **Communication channels (→ Condition E):** Can free-form messaging substitute for perfect information? Will agents lie?
3. **n/2 optimal strategy:** No agent in A/B/C discovered that ~10 coins is the maximally robust balance. Would an agent explicitly told about modular arithmetic reason its way there? Is this worth testing as a Condition A′?
4. **Underflow exploit closure:** The accelerationist's coin-printing cycle in Condition C seed 42 (ticks 11–29) is now impossible under the fixed code. Any re-run of Condition C will produce different behavior from the archived logs.
5. **Weaponised gifts without underflow:** The transfer-triggered overflow attack is still possible (and mechanically verified in heuristic runs). The question is whether LLM agents discover it deliberately.

---

## Implementation Order

```
1. Add unbounded flag to Environment / ModuloCoin        (1–2 hours)
2. Add unbounded flag support to run_experiment.py       (~30 min)
3. Run capitalism baseline (5 seeds × 3 conditions)      (API time)
4. Run modulo completions (3 more seeds × 3 conditions)  (API time)
5. Compute comparison table                              (~1 hour)
6. Decide: does modulo underperform? → D / E / F or done
```
