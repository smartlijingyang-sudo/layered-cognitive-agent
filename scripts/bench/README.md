# Benchmarks

PR-3 latency budgets live here.  Each script is a standalone
executable; the surrounding pytest tree mirrors the budget when a
test is the preferred surface.

| Script | What it measures | Acceptance gate |
|---|---|---|
| `fanout_parallel.py` | 5 concurrent `runCommand`-shaped sandbox calls through `SandboxPool` | Wall time `<200ms` (vs ~220ms pre-PR-3 serial) |

## `fanout_parallel.py`

```bash
python scripts/bench/fanout_parallel.py
python scripts/bench/fanout_parallel.py --calls 10 --per-call-ms 25 --budget-ms 200
```

Exit code 0 ⇒ under budget; non-zero ⇒ regression.  JSON summary is
printed to stdout for downstream collection.
