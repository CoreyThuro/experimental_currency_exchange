#!/usr/bin/env python3
"""
Phase 3 validation run.

Runs 2 WorkThenBuy, 2 AccumulateHigh, 1 TransferOnSignal, and 1 CycleThrough
for up to 200 ticks. Checks all five plan validation criteria and prints tuning
hints if any fail.  Run directly:

    python -m modulo_dilemma.run_heuristic
"""

import sys
from pathlib import Path

from . import DATA_DIR
from .bots import (
    BUY_RATE_THRESHOLD,
    CycleThroughBot,
    HoarderBot,
    SaboteurBot,
    SpenderBot,
)
from .environment import Environment

# Agent roster: (agent_id, role_label)
# Role labels match plan terminology: WorkThenBuy, AccumulateHigh, TransferOnSignal, CycleThrough
ROSTER = [
    ("workthenbuy_1",    "workthenbuy"),
    ("workthenbuy_2",    "workthenbuy"),
    ("accumulate_1",     "accumulate"),
    ("accumulate_2",     "accumulate"),
    ("transferonsignal", "transferonsignal"),
    ("cyclethrough",     "cyclethrough"),
]


# ── Simulation runner ─────────────────────────────────────────────────────────

def run_simulation(
    seed: int = 42,
    log_path: Path | None = None,
    energy_drain: int | None = None,
) -> tuple[dict, list[dict]]:
    """
    Run the heuristic simulation.  Optionally override ENERGY_DRAIN for tuning.
    Returns (summary_dict, tick_logs).
    """
    sim = Environment(log_path=log_path, seed=seed, energy_drain=energy_drain)
    for agent_id, _ in ROSTER:
        sim.add_agent(agent_id)

    bots: dict = {
        "workthenbuy_1":    SpenderBot(),
        "workthenbuy_2":    SpenderBot(),
        "accumulate_1":     HoarderBot(),
        "accumulate_2":     HoarderBot(),
        "transferonsignal": SaboteurBot(sim.ledger),
        "cyclethrough":     CycleThroughBot(),
    }

    tick_logs = sim.run(lambda agent_id, obs: bots[agent_id].decide(agent_id, obs))
    return sim.summary(), tick_logs


# ── Validation checks ─────────────────────────────────────────────────────────

def validate(summary: dict, tick_logs: list[dict]) -> dict[str, dict]:
    stats = summary["agent_stats"]
    by_role: dict[str, list[str]] = {}
    for agent_id, role in ROSTER:
        by_role.setdefault(role, []).append(agent_id)

    # Check 1 — Differentiated outcomes: per-strategy lifespan spread >= 10 ticks
    role_avg: dict[str, float] = {
        role: sum(stats[a]["ticks_survived"] for a in aids) / len(aids)
        for role, aids in by_role.items()
    }
    lifespan_spread = max(role_avg.values()) - min(role_avg.values())

    # Check 2 — TransferOnSignal caused at least one receiver overflow via transfer
    transfer_kills = 0
    for tl in tick_logs:
        targets_hit = {
            a["target_id"]
            for a in tl.get("actions", [])
            if a.get("type") == "transfer" and a.get("agent_id") == "transferonsignal"
        }
        for w in tl.get("wraparounds", []):
            if w["direction"] == "overflow" and w["agent_id"] in targets_hit:
                transfer_kills += 1

    # Check 3 — CycleThrough is viable: survives >= 50% of WorkThenBuy's average
    workthenbuy_avg = role_avg["workthenbuy"]
    cyclethrough_ticks = stats["cyclethrough"]["ticks_survived"]

    # Check 4 — Average lifespan 50–150 ticks
    all_lifespans = [s["ticks_survived"] for s in stats.values()]
    avg_life = sum(all_lifespans) / len(all_lifespans)

    # Check 5 — Bank rate sensitivity: bots buy more at high rates than low rates
    high_rate_ticks = low_rate_ticks = 0
    high_rate_buys = low_rate_buys = 0
    for tl in tick_logs:
        rate = tl["bank_rate"]
        buys = sum(1 for a in tl.get("actions", []) if a.get("type") == "buy_energy")
        if rate >= BUY_RATE_THRESHOLD:
            high_rate_ticks += 1
            high_rate_buys += buys
        else:
            low_rate_ticks += 1
            low_rate_buys += buys
    buys_per_tick_high = high_rate_buys / high_rate_ticks if high_rate_ticks else 0.0
    buys_per_tick_low = low_rate_buys / low_rate_ticks if low_rate_ticks else 0.0

    return {
        "check_1_differentiated_outcomes": {
            "pass": lifespan_spread >= 10,
            "lifespan_spread_ticks": round(lifespan_spread, 1),
            "role_avg_lifespans": {r: round(v, 1) for r, v in role_avg.items()},
        },
        "check_2_transfer_triggered_overflow": {
            "pass": transfer_kills > 0,
            "overflow_events_caused": transfer_kills,
        },
        "check_3_cyclethrough_viable": {
            "pass": cyclethrough_ticks >= workthenbuy_avg * 0.5,
            "cyclethrough_ticks": cyclethrough_ticks,
            "workthenbuy_avg_ticks": round(workthenbuy_avg, 1),
            "viability_threshold": round(workthenbuy_avg * 0.5, 1),
        },
        "check_4_avg_lifespan_in_range": {
            "pass": 50 <= avg_life <= 150,
            "avg_ticks": round(avg_life, 1),
            "target_range": "50–150",
        },
        "check_5_bank_rate_influences_buys": {
            "pass": buys_per_tick_high > buys_per_tick_low,
            "buys_per_tick_high_rate": round(buys_per_tick_high, 3),
            "buys_per_tick_low_rate": round(buys_per_tick_low, 3),
            "threshold": BUY_RATE_THRESHOLD,
        },
    }


# ── Auto-tuning ───────────────────────────────────────────────────────────────

class TuningFailure(RuntimeError):
    """Raised when no ENERGY_DRAIN candidate satisfies all five validation checks."""
    def __init__(self, candidates: list[int], best_drain: int, best_checks: dict) -> None:
        failed = [k for k, v in best_checks.items() if not v["pass"]]
        super().__init__(
            f"Tuning exhausted candidates {candidates}; "
            f"best result (drain={best_drain}) still failed: {failed}"
        )
        self.best_drain = best_drain
        self.best_checks = best_checks


def tune_and_run(seed: int = 42) -> tuple[dict, list[dict], dict, int]:
    """
    Search for an ENERGY_DRAIN value where all five validation checks pass.
    Tries candidates in order; raises TuningFailure if none succeed.
    Returns (summary, tick_logs, checks, drain_used).
    """
    candidates = [5, 4, 3, 2, 1, 6, 7, 8]
    best_summary, best_logs, best_checks, best_drain = None, None, None, candidates[0]

    for drain in candidates:
        summary, tick_logs = run_simulation(seed=seed, energy_drain=drain)
        checks = validate(summary, tick_logs)
        all_pass = all(c["pass"] for c in checks.values())
        if all_pass:
            return summary, tick_logs, checks, drain

        avg = checks["check_4_avg_lifespan_in_range"]["avg_ticks"]
        failed = [k for k, v in checks.items() if not v["pass"]]
        print(f"  drain={drain}: avg lifespan={avg}  failed={failed}")

        if best_summary is None or len(failed) < len(
            [k for k, v in best_checks.items() if not v["pass"]]
        ):
            best_summary, best_logs, best_checks, best_drain = (
                summary, tick_logs, checks, drain
            )

    raise TuningFailure(candidates, best_drain, best_checks)


# ── Report printing ───────────────────────────────────────────────────────────

SEP = "─" * 56


def print_report(
    summary: dict,
    checks: dict,
    drain_used: int,
    log_path: Path | None = None,
) -> None:
    stats = summary["agent_stats"]

    print(f"\n{SEP}")
    print("  HEURISTIC SIMULATION — PHASE 3 RESULTS")
    print(SEP)
    print(f"  Ticks completed : {summary['total_ticks']}")
    print(f"  ENERGY_DRAIN    : {drain_used}")
    print(f"  Survivors       : {summary['survivors'] or 'none'}")
    if log_path:
        print(f"  Log written to  : {log_path}")

    print(f"\n  {'AGENT':<16} {'TICKS':>6} {'COINS':>6} {'WRAPS':>6}  STATUS")
    print(f"  {'─'*48}")
    for agent_id, role in ROSTER:
        s = stats[agent_id]
        status = "alive" if s["alive"] else "dead"
        print(
            f"  {agent_id:<16} {s['ticks_survived']:>6} "
            f"{s['final_coins']:>6} {s['wraparounds_experienced']:>6}  {status}"
        )

    print(f"\n  VALIDATION CHECKS")
    print(f"  {'─'*48}")
    all_pass = True
    for name, result in checks.items():
        icon = "✓" if result["pass"] else "✗"
        if not result["pass"]:
            all_pass = False
        details = "  ".join(f"{k}={v}" for k, v in result.items() if k != "pass")
        print(f"  [{icon}] {name}")
        print(f"        {details}")

    print(f"\n  {'ALL CHECKS PASS ✓' if all_pass else 'SOME CHECKS FAILED'}")
    print(SEP)

    if not all_pass:
        _print_tuning_hints(checks, drain_used)


def _print_tuning_hints(checks: dict, drain_used: int) -> None:
    print("\n  TUNING HINTS")
    print(f"  {'─'*48}")

    if not checks["check_1_differentiated_outcomes"]["pass"]:
        spread = checks["check_1_differentiated_outcomes"]["lifespan_spread_ticks"]
        print(f"  Lifespan spread {spread} ticks — strategies are too similar.")
        print("  → Check that AccumulateHigh's coin target and TransferOnSignal's")
        print("    detection threshold create real differentiation.")

    if not checks["check_2_transfer_triggered_overflow"]["pass"]:
        print("  TransferOnSignal never triggered a receiver overflow.")
        print("  → Verify AccumulateHigh reaches near MODULUS and is detected.")

    if not checks["check_3_cyclethrough_viable"]["pass"]:
        c3 = checks["check_3_cyclethrough_viable"]
        print(f"  CycleThrough ({c3['cyclethrough_ticks']} ticks) died too fast vs "
              f"WorkThenBuy ({c3['workthenbuy_avg_ticks']} avg).")
        print("  → Wraparound may be mechanically punishing — review CycleThrough thresholds.")

    c4 = checks["check_4_avg_lifespan_in_range"]
    if not c4["pass"]:
        avg = c4["avg_ticks"]
        if avg < 50:
            print(f"  Avg lifespan {avg} ticks is too short.")
            print(f"  → Reduce ENERGY_DRAIN (currently {drain_used}).")
        else:
            print(f"  Avg lifespan {avg} ticks is too long — no pressure.")
            print(f"  → Increase ENERGY_DRAIN (currently {drain_used}).")

    if not checks["check_5_bank_rate_influences_buys"]["pass"]:
        c5 = checks["check_5_bank_rate_influences_buys"]
        print("  Bank rate not influencing buy decisions.")
        print(f"  buys/tick at high rate={c5['buys_per_tick_high_rate']}  "
              f"low rate={c5['buys_per_tick_low_rate']}")
        print(f"  → Check BUY_RATE_THRESHOLD={c5['threshold']} in bots.py.")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    log = DATA_DIR / "heuristic_run.jsonl"
    print("Running Phase 3 heuristic simulation…")
    print("Auto-tuning ENERGY_DRAIN if any check fails.\n")

    try:
        summary, tick_logs, checks, drain_used = tune_and_run(seed=42)
    except TuningFailure as exc:
        print(f"\nTUNING FAILED: {exc}")
        sys.exit(2)

    # Write final log with the winning drain value
    run_simulation(seed=42, log_path=log, energy_drain=drain_used)

    print_report(summary, checks, drain_used, log_path=log)
    sys.exit(0 if all(c["pass"] for c in checks.values()) else 1)
