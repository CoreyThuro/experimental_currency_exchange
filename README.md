# Modulo Dilemma

A multi-agent simulation of an economy whose currency uses modular arithmetic. Coin
balances are always in `[0, 20)`, and receiving coins past the top wraps the balance
around to the low end. Agents must keep their energy above zero by working for coins
and buying energy from a bank whose rate changes every tick.

The project asks how agents (first hard-coded bots, then LLM agents) reason about
these mechanics, and whether a modulo economy keeps its population alive as well as
an otherwise identical economy with unbounded currency. See [docs/plan.md](docs/plan.md)
for the full design.

## Layout

```
modulo_dilemma/        simulation package
  modulo_coin.py         wallet with modular (or unbounded) arithmetic
  ledger.py              public ledger
  environment.py         tick loop, bank, actions, death, logging
  bots.py                heuristic bots for mechanical validation
  llm_agent.py           LLM agent: prompts, tool schema, response parsing
  run_heuristic.py       Phase 3 bot validation run
  run_experiment.py      LLM experiment runner (conditions A–D2, --unbounded)
tests/                 pytest suite
docs/                  design plan, results report, next steps
data/
  heuristic_run.jsonl    output of the bot validation run
  runs/                  new LLM runs (created on first run)
  legacy/                earlier LLM runs; see data/legacy/README.md before using
```

## Setup

Requires Python 3.10+.

```
pip install -e ".[dev]"
export ANTHROPIC_API_KEY=...
```

## Running

```
pytest                                                    # tests
python -m modulo_dilemma.run_heuristic                    # bot validation
python -m modulo_dilemma.run_experiment --condition A --runs 5 --seed 100
python -m modulo_dilemma.run_experiment --unbounded       # capitalism baseline (A, B)
```

| Condition | Agents get |
|---|---|
| A | Rules and own state only |
| B | A + a reflection prompt about other agents |
| C | B + a cultural archetype per agent |
| D / D1 / D2 | A + other agents' coins and energy / energy only / coins only |

Each run writes a per-tick log, a reasoning log and a `.meta.json` file (config, system
prompts, code hashes) to `data/runs/modulo/` or `data/runs/unbounded/`. The runner
refuses to overwrite existing files unless `--overwrite` is passed.
