"""Test concurrency isolation for per-run Session bindings.

Pins the architectural invariant:
Multiple concurrent runs executing in separate asyncio tasks MUST NOT
overwrite or pollute each other's publish or observe Session bindings.
"""

from __future__ import annotations

import asyncio

import pytest

from lca.infrastructure.session import bindings
from lca.loop.emit.spine.ep import publish_spine_ep
from lca.plugins.events import _session_observe
from lca.plugins.events.publishers import _session_publish
from lca.session.append import Session
from lca.session.lifecycle.bind import RunEventSessionBridge


@pytest.mark.asyncio
async def test_concurrent_tasks_active_publish_session_isolation() -> None:
    """Two concurrent asyncio tasks bind different sessions and assert zero leakage."""
    session_a = Session("run_task_a")
    bridge_a = RunEventSessionBridge(session_a)
    session_b = Session("run_task_b")
    bridge_b = RunEventSessionBridge(session_b)

    step_barrier_1 = asyncio.Event()
    step_barrier_2 = asyncio.Event()

    async def worker_a() -> None:
        token_a = _session_publish.set_publish_session(bridge_a)
        try:
            assert bindings.active_publish_session() is bridge_a
            # Signal worker_b that worker_a has set its session
            step_barrier_1.set()
            # Wait for worker_b to also set its session
            await step_barrier_2.wait()
            # Interleave: yield execution
            await asyncio.sleep(0.01)

            # Invariant: worker_a still sees bridge_a, NOT bridge_b!
            assert bindings.active_publish_session() is bridge_a

            publish_spine_ep(
                "kernel.run.start",
                {"run_id": "run_task_a", "trace_id": "trace_a"},
                actor="transport",
            )
            # Event MUST land in session_a
            events_a = session_a.snapshot_events()
            assert any(e.type == "spine.kernel.run.start" for e in events_a)
        finally:
            _session_publish.reset_publish_session(token_a)

    async def worker_b() -> None:
        # Wait for worker_a to set its session first
        await step_barrier_1.wait()
        token_b = _session_publish.set_publish_session(bridge_b)
        try:
            assert bindings.active_publish_session() is bridge_b
            # Signal worker_a that worker_b has set its session
            step_barrier_2.set()
            # Interleave: yield execution
            await asyncio.sleep(0.02)

            # Invariant: worker_b still sees bridge_b, NOT bridge_a!
            assert bindings.active_publish_session() is bridge_b

            publish_spine_ep(
                "kernel.run.start",
                {"run_id": "run_task_b", "trace_id": "trace_b"},
                actor="transport",
            )
            events_b = session_b.snapshot_events()
            assert any(e.type == "spine.kernel.run.start" for e in events_b)
        finally:
            _session_publish.reset_publish_session(token_b)

    # Run both tasks concurrently
    await asyncio.gather(worker_a(), worker_b())

    # Invariant: events in session_a do NOT contain run_task_b events, and vice versa
    assert not any(e.data.get("run_id") == "run_task_b" for e in session_a.snapshot_events())
    assert not any(e.data.get("run_id") == "run_task_a" for e in session_b.snapshot_events())


@pytest.mark.asyncio
async def test_worker_a_reset_does_not_clear_worker_b_session() -> None:
    """When task A finishes and resets, task B must NOT lose its active session."""
    session_a = Session("run_short")
    bridge_a = RunEventSessionBridge(session_a)
    session_b = Session("run_long")
    bridge_b = RunEventSessionBridge(session_b)

    a_finished = asyncio.Event()

    async def short_worker() -> None:
        token = _session_publish.set_publish_session(bridge_a)
        assert bindings.active_publish_session() is bridge_a
        _session_publish.reset_publish_session(token)
        a_finished.set()

    async def long_worker() -> None:
        token = _session_publish.set_publish_session(bridge_b)
        try:
            # Wait until short_worker finishes and unbinds its session
            await a_finished.wait()
            await asyncio.sleep(0.01)

            # Invariant: long_worker still has bridge_b! Not None!
            assert bindings.active_publish_session() is bridge_b
        finally:
            _session_publish.reset_publish_session(token)

    await asyncio.gather(short_worker(), long_worker())


@pytest.mark.asyncio
async def test_concurrent_session_observe_target_isolation() -> None:
    """_session_observe.current_session() must be isolated per asyncio task."""
    session_a = Session("run_obs_a")
    bridge_a = RunEventSessionBridge(session_a)
    session_b = Session("run_obs_b")
    bridge_b = RunEventSessionBridge(session_b)

    barrier = asyncio.Event()

    async def obs_worker_a() -> None:
        _session_observe.set_session(bridge_a)
        try:
            barrier.set()
            await asyncio.sleep(0.02)
            assert _session_observe.current_session() is bridge_a
        finally:
            _session_observe.set_session(None)

    async def obs_worker_b() -> None:
        await barrier.wait()
        _session_observe.set_session(bridge_b)
        try:
            await asyncio.sleep(0.01)
            assert _session_observe.current_session() is bridge_b
        finally:
            _session_observe.set_session(None)

    await asyncio.gather(obs_worker_a(), obs_worker_b())
