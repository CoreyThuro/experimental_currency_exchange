# Legacy runs (May–June 2026)

These logs were produced by earlier versions of the code. They are kept for reference.
**Do not pool them with new runs** in `data/runs/`, because the agents were working with
different information.

| Directory | Contents |
|---|---|
| `modulo/` | Conditions A, B, C, D, D1, D2, seeds 42–46 |
| `unbounded/` | Capitalism baseline, conditions A and B, seeds 42–46 |

## Known issues

All runs were generated before these prompt and harness fixes:

- **Agents were not told their own ID.** The prompt never said "you are agent_N", and
  the alive-agent list included the agent itself. Agents could not tell their own
  ledger entries from other agents' entries. In condition C, some agents sent transfers
  to themselves while describing the target as an ally.
- **The energy drain was not stated.** Agents were told energy "drains by a fixed
  amount", not that it is 5 per tick and is applied before they act. Many deaths
  (especially in B) follow the same pattern: the agent works down to about 3 energy and
  is removed by the next drain. The drain was 5 in every run.
- **Invalid transfers were silently redirected.** A transfer to self or to an unknown
  target was changed into a transfer to the first other living agent. The tick logs
  record it as a real transfer. This affected 14 transfers in condition C, seeds 44–46.
- **Work effort level was not shown** in the prompt's ledger view.
- **No per-run metadata.** These runs have no record of model, prompt or code version.

Additional issues for specific runs:

- **Modulo A/B/C, seeds 42–43** ran before the overspend fix. Spending or transferring
  more coins than held wrapped by underflow instead of being rejected. C seeds 42–43
  contain 11 underflow events that the current code cannot produce.
- **Reasoning logs for modulo A/B/C** (`reasoning_condition_{A,B,C}.jsonl`) contain only
  seeds 44–46. The reasoning for seeds 42–43 was overwritten by a later run, so the
  quotes from those seeds in `docs/initial-outcomes.md` can no longer be checked
  against the logs.
