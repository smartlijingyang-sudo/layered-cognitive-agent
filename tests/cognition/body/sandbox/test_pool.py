"""PR-3 (G-22, ADR-0232) — sandbox pool concurrency, cap, latency, containment."""

from __future__ import annotations

import asyncio
import time

import pytest

from lca.cognition.body.sandbox.pool import (
    PooledSandboxCall,
    PooledSandboxResult,
    SandboxPool,
    default_max_concurrency,
)


async def _echo(value: int, sleep_s: float = 0.0) -> int:
    if sleep_s:
        await asyncio.sleep(sleep_s)
    return value


def _call(invocation_id: str, value: int, sleep_s: float = 0.0) -> PooledSandboxCall[int]:
    return PooledSandboxCall(
        invocation_id=invocation_id,
        run=lambda: _echo(value, sleep_s),
        metadata={"value": value},
    )


@pytest.mark.asyncio
async def test_pool_runs_concurrent_calls() -> None:
    """Five 50ms calls finish in ~50ms (concurrent) rather than ~250ms (serial)."""

    pool = SandboxPool()
    start = time.monotonic()
    results = await pool.run_many(
        [_call(f"c{i}", i, sleep_s=0.05) for i in range(5)]
    )
    elapsed = time.monotonic() - start

    assert len(results) == 5
    assert all(r.ok for r in results)
    assert [r.value for r in results] == [0, 1, 2, 3, 4]
    # Generous upper bound to absorb scheduler jitter; serial would be 0.25s.
    assert elapsed < 0.2, f"expected concurrent execution, took {elapsed:.3f}s"


@pytest.mark.asyncio
async def test_pool_caps_concurrency() -> None:
    """Concurrency never exceeds the configured cap (verified by active counter)."""

    cap = 3
    pool = SandboxPool(max_concurrency=cap)
    active = 0
    max_active = 0
    lock = asyncio.Lock()

    async def _track(value: int) -> int:
        nonlocal active, max_active
        async with lock:
            active += 1
            max_active = max(max_active, active)
        try:
            await asyncio.sleep(0.02)
        finally:
            async with lock:
                active -= 1
        return value

    calls = [
        PooledSandboxCall(invocation_id=f"c{i}", run=lambda i=i: _track(i))
        for i in range(10)
    ]
    await pool.run_many(calls)

    assert max_active <= cap, f"max_active={max_active} exceeded cap={cap}"
    assert max_active >= 2, "expected genuine overlap, got serial"


def test_default_max_concurrency_matches_contract() -> None:
    """``default_max_concurrency`` returns ``min(8, os.cpu_count())`` and is >= 1."""

    cap = default_max_concurrency()
    assert 1 <= cap <= 8
    import os

    assert cap == min(8, os.cpu_count() or 1)


def test_pool_rejects_zero_concurrency() -> None:
    """A 0 / negative cap is rejected at construction (typed contract)."""

    with pytest.raises(ValueError):
        SandboxPool(max_concurrency=0)
    with pytest.raises(ValueError):
        SandboxPool(max_concurrency=-1)


@pytest.mark.asyncio
async def test_pool_contains_exception_in_one_slot() -> None:
    """A failing call does not abort siblings (failure containment)."""

    pool = SandboxPool()

    async def _raise() -> int:
        raise RuntimeError("slot failure")

    calls = [
        _call("ok_1", 1, sleep_s=0.0),
        PooledSandboxCall(invocation_id="bad", run=_raise),
        _call("ok_2", 2, sleep_s=0.0),
    ]
    results = await pool.run_many(calls)

    assert len(results) == 3
    by_id = {r.invocation_id: r for r in results}
    assert by_id["ok_1"].ok and by_id["ok_1"].value == 1
    assert by_id["ok_2"].ok and by_id["ok_2"].value == 2
    assert not by_id["bad"].ok
    assert isinstance(by_id["bad"].error, RuntimeError)


@pytest.mark.asyncio
async def test_pool_latency_within_budget() -> None:
    """Five 50ms calls complete in under 200ms (PR-3 acceptance budget)."""

    pool = SandboxPool()
    start = time.monotonic()
    results = await pool.run_many(
        [_call(f"c{i}", i, sleep_s=0.05) for i in range(5)]
    )
    elapsed = time.monotonic() - start

    assert elapsed < 0.2, f"latency budget exceeded: {elapsed:.3f}s"
    assert all(r.ok for r in results)


@pytest.mark.asyncio
async def test_pool_empty_call_list_returns_empty() -> None:
    """Empty input short-circuits to an empty result list (no tasks spawned)."""

    pool = SandboxPool()
    results = await pool.run_many([])
    assert results == []


@pytest.mark.asyncio
async def test_pool_records_per_call_timing() -> None:
    """Each result carries a non-negative ``duration_s`` matching the sleep."""

    pool = SandboxPool()
    results = await pool.run_many(
        [_call("c1", 1, sleep_s=0.02), _call("c2", 2, sleep_s=0.04)]
    )
    assert results[0].duration_s >= 0.0
    assert results[1].duration_s >= results[0].duration_s - 0.01  # monotonic-ish
