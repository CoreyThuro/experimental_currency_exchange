#!/usr/bin/env python3
"""
Phase 4 experiment runner.

Runs Conditions A, B, and C of the Modulo Dilemma LLM experiment, each over
N_RUNS independent simulations, then prints a cross-condition comparison.

    python -m modulo_dilemma.run_experiment                  # A, B, C; 5 runs each
    python -m modulo_dilemma.run_experiment --condition A    # single condition
    python -m modulo_dilemma.run_experiment --runs 2         # quick smoke-test

Each run writes three files to data/runs/modulo/ (or data/runs/unbounded/):
    condition_<C>_seed<N>.jsonl              per-tick simulation log
    reasoning_condition_<C>_seed<N>.jsonl    per-decision LLM reasoning
    condition_<C>_seed<N>.meta.json          config, system prompts, code hashes
Existing files are never overwritten unless --overwrite is passed.
"""

import argparse
import hashlib
import json
import platform
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import anthropic
import pydantic

from . import DATA_DIR
from . import environment as env_mod
from .environment import Environment, TOTAL_TICKS
from .llm_agent import ARCHETYPES, Condition, LLMAgent

# ── Experiment configuration ──────────────────────────────────────────────────

N_AGENTS = 3
N_RUNS = 5
BASE_SEED = 42
LOG_DIR = DATA_DIR / "runs" / "modulo"
LOG_DIR_UNBOUNDED = DATA_DIR / "runs" / "unbounded"

ROSTER = [f"agent_{i}" for i in range(N_AGENTS)]
ARCHETYPE_LIST = list(ARCHETYPES.keys())
ARCHETYPE_ASSIGNMENT: dict[str, str] = {
    aid: ARCHETYPE_LIST[i % len(ARCHETYPE_LIST)] for i, aid in enumerate(ROSTER)
}

# Source files whose contents determine simulation behaviour; hashed into each
# run's metadata so logs can be matched to the exact code that produced them.
_SOURCE_FILES = ("modulo_coin.py", "ledger.py", "environment.py", "llm_agent.py", "run_experiment.py")

# ── Log file layout and provenance ────────────────────────────────────────────

def run_paths(log_dir: Path, condition: Condition, seed: int) -> dict[str, Path]:
    """All files written for one (condition, seed) run."""
    stem = f"condition_{condition.value}_seed{seed}"
    return {
        "ticks": log_dir / f"{stem}.jsonl",
        "reasoning": log_dir / f"reasoning_{stem}.jsonl",
        "meta": log_dir / f"{stem}.meta.json",
    }


def existing_run_files(log_dir: Path, conditions: list[Condition], seeds: list[int]) -> list[Path]:
    return [
        p
        for c in conditions
        for s in seeds
        for p in run_paths(log_dir, c, s).values()
        if p.exists()
    ]


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _code_hashes() -> dict[str, str]:
    root = Path(__file__).resolve().parent
    return {name: _sha256((root / name).read_text()) for name in _SOURCE_FILES}


def build_run_metadata(
    condition: Condition,
    seed: int,
    sim: Environment,
    agents: dict[str, "LLMAgent"],
    unbounded: bool,
    transparency: str,
) -> dict:
    return {
        "condition": condition.value,
        "seed": seed,
        "unbounded": unbounded,
        "transparency": transparency,
        "model": next(iter(agents.values())).model,
        "roster": list(ROSTER),
        "archetypes": {aid: a.archetype for aid, a in agents.items()},
        "constants": {
            "modulus": env_mod.MODULUS,
            "starting_energy": env_mod.STARTING_ENERGY,
            "energy_drain": sim.energy_drain,
            "death_threshold": env_mod.DEATH_THRESHOLD,
            "total_ticks": env_mod.TOTAL_TICKS,
            "bank_rate_min": env_mod.BANK_RATE_MIN,
            "bank_rate_max": env_mod.BANK_RATE_MAX,
            "work_table": env_mod.WORK_TABLE,
        },
        "system_prompts": {
            aid: {"sha256": _sha256(a.system_prompt), "text": a.system_prompt}
            for aid, a in agents.items()
        },
        "code_sha256": _code_hashes(),
        "versions": {
            "python": platform.python_version(),
            "anthropic": anthropic.__version__,
            "pydantic": pydantic.VERSION,
        },
        "started_at": datetime.now(timezone.utc).isoformat(),
        "completed": False,
    }


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n")

# ── Result container ──────────────────────────────────────────────────────────

@dataclass
class RunResult:
    condition: Condition
    seed: int
    tick_logs: list[dict]
    summary: dict
    agent_reasoning: dict[str, list[dict]] = field(default_factory=dict)
    agent_failures: dict[str, int] = field(default_factory=dict)

# ── Single simulation ─────────────────────────────────────────────────────────

def run_one(
    condition: Condition,
    seed: int,
    log_dir: Optional[Path] = None,
    model: Optional[str] = None,
    client: Optional[anthropic.Anthropic] = None,
    unbounded: bool = False,
) -> RunResult:
    """
    Run one simulation. If log_dir is given, writes three files for this run
    (see run_paths): per-tick log, reasoning log, and a metadata file recording
    configuration, prompts and code hashes. The metadata is written before the
    first tick with completed=false and rewritten on success, so a crashed run
    is identifiable.
    """
    transparency_map = {
        Condition.D: "full",
        Condition.D1: "energy",
        Condition.D2: "coins",
    }
    transparency = transparency_map.get(condition, "none")
    paths = run_paths(log_dir, condition, seed) if log_dir else None
    sim = Environment(
        seed=seed,
        log_path=paths["ticks"] if paths else None,
        unbounded=unbounded,
        transparency=transparency,
    )
    for aid in ROSTER:
        sim.add_agent(aid)

    agents: dict[str, LLMAgent] = {
        aid: LLMAgent(
            agent_id=aid,
            condition=condition,
            archetype=ARCHETYPE_ASSIGNMENT[aid] if condition == Condition.C else None,
            model=model,
            client=client,
            unbounded=unbounded,
            energy_drain=sim.energy_drain,
        )
        for aid in ROSTER
    }

    meta: Optional[dict] = None
    if paths:
        meta = build_run_metadata(condition, seed, sim, agents, unbounded, transparency)
        _write_json(paths["meta"], meta)

    _last_tick: list[int] = [-1]

    def _action_fn(aid: str, obs: dict):
        tick = obs["tick"]
        if tick != _last_tick[0]:
            _last_tick[0] = tick
            alive = len(obs["alive_agents"])
            failures = sum(a.failures for a in agents.values())
            print(
                f"\r    tick {tick:>3}/{TOTAL_TICKS}  alive={alive}/{len(ROSTER)}"
                f"  api_failures={failures}   ",
                end="", flush=True,
            )
        return agents[aid].decide(aid, obs)

    tick_logs = sim.run(_action_fn)
    failures_total = sum(a.failures for a in agents.values())
    print(
        f"\r    done — {sim.tick} ticks  api_failures={failures_total}"
        + " " * 20,
        flush=True,
    )
    summary = sim.summary()

    result = RunResult(
        condition=condition,
        seed=seed,
        tick_logs=tick_logs,
        summary=summary,
        agent_reasoning={aid: a.reasoning_log for aid, a in agents.items()},
        agent_failures={aid: a.failures for aid, a in agents.items()},
    )

    if paths and meta is not None:
        write_reasoning_log(result, paths["reasoning"])
        meta.update({
            "completed": True,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "ticks": sim.tick,
            "agent_failures": result.agent_failures,
        })
        _write_json(paths["meta"], meta)

    return result


def run_condition(
    condition: Condition,
    n_runs: int = N_RUNS,
    base_seed: int = BASE_SEED,
    log_dir: Optional[Path] = None,
    model: Optional[str] = None,
    client: Optional[anthropic.Anthropic] = None,
    unbounded: bool = False,
) -> list[RunResult]:
    results = []
    for i in range(n_runs):
        seed = base_seed + i
        print(f"  [{condition.value}] run {i + 1}/{n_runs} seed={seed}…", flush=True)
        result = run_one(
            condition, seed, log_dir=log_dir, model=model, client=client, unbounded=unbounded
        )
        results.append(result)
    return results

# ── Analysis ──────────────────────────────────────────────────────────────────

def detect_mutual_aid(tick_logs: list[dict]) -> int:
    """
    Count unordered agent pairs where both directions of transfer occurred
    at any point in the run — a proxy for cooperative exchange.
    """
    directed: set[tuple[str, str]] = set()
    for tl in tick_logs:
        for action in tl.get("actions", []):
            if action.get("type") == "transfer":
                directed.add((action["agent_id"], action["target_id"]))
    pairs: set[frozenset] = set()
    for sender, receiver in directed:
        if (receiver, sender) in directed:
            pairs.add(frozenset([sender, receiver]))
    return len(pairs)


def detect_weaponized_gifts(tick_logs: list[dict]) -> int:
    """Count transfers that directly caused a receiver overflow (wraparound)."""
    total = 0
    for tl in tick_logs:
        receivers_hit = {
            a["target_id"]
            for a in tl.get("actions", [])
            if a.get("type") == "transfer"
        }
        for w in tl.get("wraparounds", []):
            if w["direction"] == "overflow" and w["agent_id"] in receivers_hit:
                total += 1
    return total


def compute_metrics(results: list[RunResult]) -> dict:
    lifespans: list[int] = []
    mutual_aid_events = 0
    weaponized_gift_events = 0
    action_counts: dict[str, int] = {"work": 0, "buy_energy": 0, "transfer": 0, "pass": 0}
    total_failures = 0

    for result in results:
        for stats in result.summary["agent_stats"].values():
            lifespans.append(stats["ticks_survived"])
        mutual_aid_events += detect_mutual_aid(result.tick_logs)
        weaponized_gift_events += detect_weaponized_gifts(result.tick_logs)
        total_failures += sum(result.agent_failures.values())
        for tl in result.tick_logs:
            for action in tl.get("actions", []):
                atype = action.get("type", "")
                if atype in action_counts:
                    action_counts[atype] += 1

    n = len(results)
    total_actions = sum(action_counts.values()) or 1
    return {
        "avg_lifespan": round(sum(lifespans) / len(lifespans), 1) if lifespans else 0,
        "avg_mutual_aid_pairs_per_run": round(mutual_aid_events / n, 2),
        "avg_weaponized_gifts_per_run": round(weaponized_gift_events / n, 2),
        "action_mix": {k: round(v / total_actions, 3) for k, v in action_counts.items()},
        "total_llm_failures": total_failures,
        "runs": n,
    }

# ── Reporting ─────────────────────────────────────────────────────────────────

SEP = "─" * 60


def print_condition_report(condition: Condition, metrics: dict) -> None:
    print(f"\n  CONDITION {condition.value}", end="  ")
    label = {
        "A": "Myopic", "B": "Social scaffolding", "C": "Cultural archetypes",
        "D": "Transparent (full)", "D1": "Transparent (energy only)", "D2": "Transparent (coins only)",
    }
    print(f"({label[condition.value]})")
    print(f"  {'─' * 46}")
    print(f"  Runs                    : {metrics['runs']}")
    print(f"  Avg lifespan            : {metrics['avg_lifespan']} ticks")
    print(f"  Avg mutual-aid pairs    : {metrics['avg_mutual_aid_pairs_per_run']}")
    print(f"  Avg weaponized gifts    : {metrics['avg_weaponized_gifts_per_run']}")
    mix = metrics["action_mix"]
    print(f"  Action mix              : work={mix['work']:.1%}  buy={mix['buy_energy']:.1%}  "
          f"transfer={mix['transfer']:.1%}  pass={mix['pass']:.1%}")
    print(f"  LLM failures (fallback) : {metrics['total_llm_failures']}")


def print_comparison(all_metrics: dict[str, dict]) -> None:
    print(f"\n{SEP}")
    print("  CROSS-CONDITION COMPARISON")
    print(SEP)

    conds = list(all_metrics.keys())
    print(f"\n  {'Metric':<30} " + "  ".join(f"{c:>8}" for c in conds))
    print(f"  {'─' * 46}")

    rows = [
        ("Avg lifespan (ticks)", "avg_lifespan"),
        ("Mutual-aid pairs / run", "avg_mutual_aid_pairs_per_run"),
        ("Weaponized gifts / run", "avg_weaponized_gifts_per_run"),
    ]
    for label, key in rows:
        vals = "  ".join(f"{all_metrics[c][key]:>8}" for c in conds)
        print(f"  {label:<30} {vals}")

    print(f"\n  Action mix breakdown:")
    for action in ("work", "buy_energy", "transfer", "pass"):
        vals = "  ".join(
            f"{all_metrics[c]['action_mix'][action]:>7.1%}" for c in conds
        )
        print(f"    {action:<28} {vals}")

    print(f"\n{SEP}")


def write_reasoning_log(result: RunResult, path: Path) -> None:
    """Write one run's reasoning to its own per-seed file (see run_paths)."""
    cond = result.condition.value
    with open(path, "w") as f:
        for aid, log in result.agent_reasoning.items():
            for entry in log:
                f.write(json.dumps({
                    "condition": cond,
                    "seed": result.seed,
                    "agent_id": aid,
                    "archetype": ARCHETYPE_ASSIGNMENT.get(aid) if cond == "C" else None,
                    **entry,
                }) + "\n")
    print(f"    reasoning log: {path}")

# ── Entry point ───────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Phase 4/5 LLM experiment")
    parser.add_argument(
        "--condition", choices=["A", "B", "C", "D", "D1", "D2"], default=None,
        help="Run a single condition (D=full transparency, D1=energy only, D2=coins only)"
    )
    parser.add_argument("--runs", type=int, default=N_RUNS, help="Simulations per condition")
    parser.add_argument("--seed", type=int, default=BASE_SEED, help="Base random seed")
    parser.add_argument("--model", default=None, help="Override LLM model ID")
    parser.add_argument("--no-logs", action="store_true", help="Skip writing log files")
    parser.add_argument(
        "--unbounded", action="store_true",
        help="Capitalism baseline: remove coin modulus, use unbounded arithmetic"
    )
    parser.add_argument(
        "--overwrite", action="store_true",
        help="Allow replacing existing log files for the requested condition/seed runs"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    default_log_dir = LOG_DIR_UNBOUNDED if args.unbounded else LOG_DIR
    log_dir = None if args.no_logs else default_log_dir
    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)

    if args.condition:
        if args.unbounded and args.condition in ("C", "D", "D1", "D2"):
            print(f"ERROR: Condition {args.condition} cannot run in unbounded mode.")
            sys.exit(1)
        conditions = [Condition(args.condition)]
    elif args.unbounded:
        conditions = [Condition.A, Condition.B]
    else:
        conditions = [Condition.A, Condition.B, Condition.C]

    if log_dir and not args.overwrite:
        seeds = [args.seed + i for i in range(args.runs)]
        clashes = existing_run_files(log_dir, conditions, seeds)
        if clashes:
            print("ERROR: these log files already exist and would be overwritten:")
            for p in clashes:
                print(f"  {p}")
            print("Choose a different --seed, archive the files, or pass --overwrite.")
            sys.exit(1)

    client = anthropic.Anthropic()
    all_metrics: dict[str, dict] = {}

    mode_label = "CAPITALISM BASELINE (unbounded)" if args.unbounded else "MODULO DILEMMA"
    print(f"\n{SEP}")
    print(f"  PHASE 4/5 — LLM AGENT EXPERIMENT — {mode_label}")
    print(SEP)

    for condition in conditions:
        print(f"\nRunning Condition {condition.value}…")
        results = run_condition(
            condition,
            n_runs=args.runs,
            base_seed=args.seed,
            log_dir=log_dir,
            model=args.model,
            client=client,
            unbounded=args.unbounded,
        )
        metrics = compute_metrics(results)
        all_metrics[condition.value] = metrics
        print_condition_report(condition, metrics)

    if len(all_metrics) > 1:
        print_comparison(all_metrics)

    sys.exit(0)
