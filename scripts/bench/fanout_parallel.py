"""scripts/bench/fanout_parallel.py — PR-3 (G-22, ADR-0232) acceptance gate.

Five concurrent ``runCommand``-shaped sandbox calls should complete
within the <200ms wall budget that was the original B-3 motivation.
This benchmark exercises the new ``SandboxPool`` directly with synthetic
50ms-per-call payloads (representative of an LCA read-only tool), then
reports per-call latency and the overall wall time.

Usage::

    python scripts/bench/fanout_parallel.py
    python scripts/bench/fanout_parallel.py --calls 10 --per-call-ms 25

Exit codes:
    0 — every call completed within budget (<200ms wall).
    1 — wall time exceeded budget (PR-3 regression signal).

The benchmark is a script, not a test, so it can be run on a developer
machine without pytest.  A pytest mirror lives under
``tests/integration/test_benchmark_*.py`` (added in a follow-up if
requested); the script itself is the canonical source of truth.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

# Make the repo importable when invoked from the worktree root.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from lca.cognition.body.sandbox.pool import (  # noqa: E402
    PooledSandboxCall,
    SandboxPool,
    default_max_concurrency,
)


async def _fake_run_command(call_index: int, sleep_s: float) -> dict[str, float]:
    """Stand-in for a real ``runCommand`` sandbox invocation."""

    start = time.monotonic()
    await asyncio.sleep(sleep_s)
    elapsed = time.monotonic() - start
    return {"call_index": call_index, "latency_s": elapsed}


async def _run(call_count: int, per_call_ms: int, budget_ms: int) -> int:
    pool = SandboxPool()
    sleep_s = per_call_ms / 1000.0
    calls = [
        PooledSandboxCall(
            invocation_id=f"bench_{i}",
            run=lambda i=i: _fake_run_command(i, sleep_s),
        )
        for i in range(call_count)
    ]

    wall_start = time.monotonic()
    results = await pool.run_many(calls)
    wall_elapsed_ms = (time.monotonic() - wall_start) * 1000

    per_call_ms_list = [r.duration_s * 1000 for r in results]
    ok_count = sum(1 for r in results if r.ok)

    summary = {
        "call_count": call_count,
        "ok_count": ok_count,
        "per_call_ms_mean": statistics.fmean(per_call_ms_list),
        "per_call_ms_max": max(per_call_ms_list),
        "wall_elapsed_ms": wall_elapsed_ms,
        "budget_ms": budget_ms,
        "max_concurrency": pool.max_concurrency,
        "default_max_concurrency": default_max_concurrency(),
        "under_budget": wall_elapsed_ms < budget_ms,
    }
    print(json.dumps(summary, indent=2))

    await pool.aclose()
    return 0 if summary["under_budget"] and ok_count == call_count else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PR-3 fanout_parallel benchmark")
    parser.add_argument("--calls", type=int, default=5, help="number of sandbox calls")
    parser.add_argument(
        "--per-call-ms",
        type=int,
        default=50,
        help="per-call synthetic latency in ms",
    )
    parser.add_argument(
        "--budget-ms",
        type=int,
        default=200,
        help="overall wall-time budget in ms (PR-3 acceptance gate)",
    )
    args = parser.parse_args(argv)
    return asyncio.run(_run(args.calls, args.per_call_ms, args.budget_ms))


if __name__ == "__main__":
    raise SystemExit(main())
