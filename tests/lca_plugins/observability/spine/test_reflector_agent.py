"""Tests for agent-layer spine reflector (PR-3.1).

Asserts that ``CognitiveAgent.run`` / ``CognitiveAgent.resume`` wrap
each iteration with the canonical
``agent_loop.iteration.start`` / ``agent_loop.iteration.end`` events,
and that the emit helpers are safe no-ops when no spine is wired.

The pattern mirrors the cognition reflector test
(``test_reflector_cognition.py``): helpers read the process-local
active spine installed by ``set_active_spine`` and call
``spine.append(...)``.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from lca.infrastructure.observability.spine.context import SpineContext
from lca.infrastructure.observability.spine.event_record import EventRecord
from lca.infrastructure.observability.spine.event_spine import EventSpine


def _run(coro):
    """Run an awaitable synchronously (test helper)."""
    return asyncio.new_event_loop().run_until_complete(coro)


# ── helpers ──────────────────────────────────────────────────────────


class _CaptureSink:
    """Minimal sink that records every EventRecord in order."""

    def __init__(self) -> None:
        self.records: list[EventRecord] = []

    def write(self, record: EventRecord) -> None:
        self.records.append(record)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass


def _make_spine() -> tuple[EventSpine, _CaptureSink]:
    sink = _CaptureSink()
    spine = EventSpine(sinks=[sink])
    SpineContext.set_run("agent-reflector-test")
    return spine, sink


def _make_agent(runtime: Any) -> Any:
    """Build a CognitiveAgent bypassing __init__ for unit tests."""
    from lca.agent.cognitive_agent import CognitiveAgent
    from lca.contracts.models.core.budget import DEFAULT_MAX_STEPS
    from lca.contracts.models.team.role_team import RoleProfile, ToolPermissionManifest

    agent = CognitiveAgent.__new__(CognitiveAgent)
    agent.runtime = runtime  # type: ignore[assignment]
    agent.role_profile = RoleProfile(
        role="r",
        goal="g",
        backstory="b",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
    )
    agent._observability = None  # type: ignore[assignment]
    agent.max_steps = DEFAULT_MAX_STEPS
    agent.max_wall_clock_seconds = None
    agent._plan_ref = ""  # type: ignore[assignment]
    return agent


# ── safe no-ops without active spine ────────────────────────────────


def test_emit_helpers_are_safe_when_no_spine_wired() -> None:
    """Without an active spine, the helpers must not raise."""
    from lca.plugins.observability.spine.reflectors.agent_spawn import (
        emit_agent_loop_iteration_end,
        emit_agent_loop_iteration_start,
    )

    # Both helpers must complete without raising, regardless of state.
    emit_agent_loop_iteration_start(trace_id="t1")
    emit_agent_loop_iteration_end(trace_id="t1", outcome="success")


# ── helpers forward to active spine ──────────────────────────────────


def test_emit_helpers_forward_to_active_spine() -> None:
    """When a spine is set, helpers emit via spine.append."""
    from lca.plugins.observability.spine.reflectors.agent_spawn import (
        emit_agent_loop_iteration_end,
        emit_agent_loop_iteration_start,
        set_active_spine,
    )

    spine, sink = _make_spine()
    set_active_spine(spine)
    try:
        emit_agent_loop_iteration_start(trace_id="t1")
        emit_agent_loop_iteration_end(trace_id="t1", outcome="success")
    finally:
        set_active_spine(None)

    points = [r.execution_point for r in sink.records]
    assert points == ["agent_loop.iteration.start", "agent_loop.iteration.end"]
    assert sink.records[1].outcome == "success"


# ── CognitiveAgent.run emits agent_loop.iteration.start/end ─────────


def test_cognitive_agent_run_emits_iteration_events() -> None:
    """CognitiveAgent.run wraps with agent_loop.iteration.start/end."""
    from lca.contracts.models.core.budget import Budget
    from lca.contracts.models.core.lifecycle import TaskStatus
    from lca.contracts.models.core.result import Result
    from lca.plugins.observability.spine.reflectors.agent_spawn import set_active_spine

    class _StubRuntime:
        async def run(self, *args: Any, **kwargs: Any) -> Result:
            return Result(
                trace_id="t1",
                status=TaskStatus.COMPLETED,
                final_state_ref="",
                total_steps=1,
                budget_used=Budget(),
                output="done",
            )

    spine, sink = _make_spine()
    set_active_spine(spine)
    try:
        agent = _make_agent(_StubRuntime())
        result = _run(agent.run("hello"))
        assert result.status.value == "completed"
    finally:
        set_active_spine(None)

    points = [r.execution_point for r in sink.records]
    assert points == ["agent_loop.iteration.start", "agent_loop.iteration.end"]


# ── CognitiveAgent.run emits failure end event when inner raises ────


def test_cognitive_agent_run_emits_failure_end_on_exception() -> None:
    """If runtime.run raises, the spine still receives end with outcome='failure'."""
    from lca.plugins.observability.spine.reflectors.agent_spawn import set_active_spine

    class _ExplodingRuntime:
        async def run(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError("runtime boom")

    spine, sink = _make_spine()
    set_active_spine(spine)
    try:
        agent = _make_agent(_ExplodingRuntime())
        with pytest.raises(RuntimeError, match="runtime boom"):
            _run(agent.run("hello"))
    finally:
        set_active_spine(None)

    points = [r.execution_point for r in sink.records]
    assert points == ["agent_loop.iteration.start", "agent_loop.iteration.end"]
    assert sink.records[1].outcome == "failure"


# ── CognitiveAgent.resume emits iteration events ─────────────────────


def test_cognitive_agent_resume_emits_iteration_events() -> None:
    """CognitiveAgent.resume also wraps with iteration events (resumed turn)."""
    from lca.contracts.models.core.budget import Budget
    from lca.contracts.models.core.lifecycle import TaskStatus
    from lca.contracts.models.core.result import Result
    from lca.contracts.models.core.state import StateSnapshot
    from lca.plugins.observability.spine.reflectors.agent_spawn import set_active_spine

    class _StubRuntime:
        async def resume(self, snapshot: StateSnapshot, **kwargs: Any) -> Result:
            return Result(
                trace_id="t1",
                status=TaskStatus.COMPLETED,
                final_state_ref="",
                total_steps=1,
                budget_used=Budget(),
                output="done",
            )

    spine, sink = _make_spine()
    set_active_spine(spine)
    try:
        agent = _make_agent(_StubRuntime())
        snap = StateSnapshot(snapshot_id="snap-1", step=0, state_ref="state-ref-1")
        _run(agent.resume(snap))
    finally:
        set_active_spine(None)

    points = [r.execution_point for r in sink.records]
    assert points == ["agent_loop.iteration.start", "agent_loop.iteration.end"]


# ── resume kind tag carried through to the envelope ────────────────


def test_resume_iteration_carries_resume_kind() -> None:
    """The .start event payload tags the iteration as 'resume'."""
    from lca.contracts.models.core.budget import Budget
    from lca.contracts.models.core.lifecycle import TaskStatus
    from lca.contracts.models.core.result import Result
    from lca.contracts.models.core.state import StateSnapshot
    from lca.plugins.observability.spine.reflectors.agent_spawn import set_active_spine

    class _StubRuntime:
        async def resume(self, snapshot: StateSnapshot, **kwargs: Any) -> Result:
            return Result(
                trace_id="t1",
                status=TaskStatus.COMPLETED,
                final_state_ref="",
                total_steps=1,
                budget_used=Budget(),
                output="done",
            )

    spine, sink = _make_spine()
    set_active_spine(spine)
    try:
        agent = _make_agent(_StubRuntime())
        snap = StateSnapshot(snapshot_id="snap-1", step=0, state_ref="state-ref-1")
        _run(agent.resume(snap))
    finally:
        set_active_spine(None)

    assert sink.records[0].payload["iteration_kind"] == "resume"
    assert sink.records[1].payload["iteration_kind"] == "resume"


# ── TeamHandle.run emits team-level iteration envelope ──────────────


def test_team_handle_run_emits_iteration_events() -> None:
    """TeamHandle.run wraps with agent_loop.iteration.start/end."""
    from lca.agent.team_handle import TeamHandle
    from lca.contracts.models.core.budget import Budget
    from lca.contracts.models.core.lifecycle import TaskStatus
    from lca.contracts.models.core.result import Result
    from lca.contracts.protocols import TeamStrategy
    from lca.infrastructure.observability import TeamTraceProfile
    from lca.plugins.observability.spine.reflectors.agent_spawn import set_active_spine

    class _StubStrategy(TeamStrategy):
        async def run(self, objective: str) -> Result:
            return Result(
                trace_id="t1",
                status=TaskStatus.COMPLETED,
                final_state_ref="",
                total_steps=1,
                budget_used=Budget(),
                output="team-done",
            )

    profile = TeamTraceProfile(
        team_id="team-1",
        strategy_key="sequential",
        mandate="",
        lead_role="lead",
        member_roles=("r1", "r2"),
    )

    handle = TeamHandle(
        strategy=_StubStrategy(),
        profile=profile,
        observability=None,  # type: ignore[arg-type]
        members=(),
    )

    spine, sink = _make_spine()
    set_active_spine(spine)
    try:
        _run(handle.run("objective"))
    finally:
        set_active_spine(None)

    points = [r.execution_point for r in sink.records]
    assert points == ["agent_loop.iteration.start", "agent_loop.iteration.end"]
    # The start envelope should carry the team:<team_id> role tag.
    start_payload = sink.records[0].payload
    assert start_payload["role"] == "team:team-1"
