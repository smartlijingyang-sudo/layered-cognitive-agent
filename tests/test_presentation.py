"""Tests for the presentation plane — turn-based structured representation.

Tests the core mechanism that transforms flat journal events into
structured turns with explicit phase boundaries.
"""

from __future__ import annotations

import pytest

from gateway.presentation.tool_lifecycle import (
    InvalidTransitionError,
    ToolLifecycleMap,
)
from gateway.presentation.turn_snapshot import (
    PhaseKind,
    ToolLifecycleState,
    ToolPhase,
    Turn,
    TurnSnapshot,
)

# ── ToolLifecycleMap ────────────────────────────────────────


class TestToolLifecycleMap:
    def test_start_creates_invocation(self) -> None:
        lm = ToolLifecycleMap()
        phase = lm.start("inv_1", "execute_code", ts=100.0)
        assert phase.state == ToolLifecycleState.STARTED
        assert phase.invocation_id == "inv_1"
        assert phase.tool_name == "execute_code"
        assert phase.started_at == 100.0

    def test_valid_transition_started_to_running(self) -> None:
        lm = ToolLifecycleMap()
        lm.start("inv_1", "execute_code", ts=100.0)
        phase = lm.transition("inv_1", ToolLifecycleState.RUNNING, ts=101.0)
        assert phase.state == ToolLifecycleState.RUNNING

    def test_valid_transition_running_to_succeeded(self) -> None:
        lm = ToolLifecycleMap()
        lm.start("inv_1", "execute_code", ts=100.0)
        lm.transition("inv_1", ToolLifecycleState.RUNNING, ts=101.0)
        phase = lm.transition(
            "inv_1",
            ToolLifecycleState.SUCCEEDED,
            ts=102.0,
            plugin_state={"output": "ok"},
        )
        assert phase.state == ToolLifecycleState.SUCCEEDED
        assert phase.ended_at == 102.0
        assert phase.plugin_state == {"output": "ok"}

    def test_invalid_transition_raises(self) -> None:
        lm = ToolLifecycleMap()
        lm.start("inv_1", "execute_code", ts=100.0)
        lm.transition("inv_1", ToolLifecycleState.SUCCEEDED, ts=101.0)
        # Terminal → anything is invalid
        with pytest.raises(InvalidTransitionError):
            lm.transition("inv_1", ToolLifecycleState.RUNNING, ts=102.0)

    def test_started_can_succeed_without_running(self) -> None:
        """Quick tools (activate_skill) finish without a RUNNING phase."""
        lm = ToolLifecycleMap()
        lm.start("inv_1", "activate_skill", ts=100.0)
        phase = lm.transition(
            "inv_1",
            ToolLifecycleState.SUCCEEDED,
            ts=101.0,
            plugin_state={"content": "# Skill\n\nbody", "id": "demo"},
        )
        assert phase.state == ToolLifecycleState.SUCCEEDED
        assert phase.plugin_state["content"].startswith("# Skill")

    def test_started_to_denied(self) -> None:
        lm = ToolLifecycleMap()
        lm.start("inv_1", "execute_code", ts=100.0)
        phase = lm.transition("inv_1", ToolLifecycleState.DENIED, ts=101.0, error="no perm")
        assert phase.state == ToolLifecycleState.DENIED
        assert phase.error == "no perm"
        assert phase.is_terminal

    def test_close_all_forces_terminal(self) -> None:
        lm = ToolLifecycleMap()
        lm.start("inv_1", "execute_code", ts=100.0)
        lm.start("inv_2", "run_command", ts=101.0)
        lm.transition("inv_1", ToolLifecycleState.RUNNING, ts=102.0)
        # inv_1 is RUNNING (not terminal), inv_2 is STARTED (not terminal)
        assert lm.open_count == 2

        lm.close_all(ts=200.0)

        assert lm.open_count == 0
        assert lm.get("inv_1").state == ToolLifecycleState.FAILED
        assert lm.get("inv_2").state == ToolLifecycleState.FAILED
        assert lm.get("inv_1").ended_at == 200.0

    def test_close_all_skips_terminal(self) -> None:
        lm = ToolLifecycleMap()
        lm.start("inv_1", "execute_code", ts=100.0)
        lm.transition("inv_1", ToolLifecycleState.RUNNING, ts=100.5)
        lm.transition("inv_1", ToolLifecycleState.SUCCEEDED, ts=101.0)
        lm.start("inv_2", "run_command", ts=102.0)
        # inv_1 already terminal, inv_2 not
        lm.close_all(ts=200.0)
        assert lm.get("inv_1").state == ToolLifecycleState.SUCCEEDED  # unchanged
        assert lm.get("inv_2").state == ToolLifecycleState.FAILED

    def test_stream_output(self) -> None:
        lm = ToolLifecycleMap()
        lm.start("inv_1", "execute_code", ts=100.0)
        lm.transition("inv_1", ToolLifecycleState.RUNNING, ts=101.0)
        lm.stream_output("inv_1", stdout="line1\n")
        lm.stream_output("inv_1", stdout="line2\n")
        lm.stream_output("inv_1", stderr="warn\n")
        assert lm.get("inv_1").stdout_buffer == "line1\nline2\n"
        assert lm.get("inv_1").stderr_buffer == "warn\n"

    def test_get_ordered(self) -> None:
        lm = ToolLifecycleMap()
        lm.start("inv_b", "b", ts=2.0)
        lm.start("inv_a", "a", ts=1.0)
        ordered = lm.get_ordered()
        assert [p.invocation_id for p in ordered] == ["inv_b", "inv_a"]


# ── TurnSnapshot ────────────────────────────────────────────


class TestTurnSnapshot:
    def test_empty_snapshot(self) -> None:
        s = TurnSnapshot()
        assert s.turns == ()
        assert s.current_turn is None
        assert s.finished is False
        assert s.steps_total == 0
        assert s.open_tool_count == 0

    def test_append_turn(self) -> None:
        s = TurnSnapshot()
        t0 = Turn(index=0, phase=PhaseKind.REASONING, reasoning_text="thinking...")
        s = s.append_turn(t0)
        assert len(s.turns) == 1
        assert s.current_turn_index == 0
        assert s.current_turn.reasoning_text == "thinking..."

    def test_replace_turn(self) -> None:
        t0 = Turn(index=0, phase=PhaseKind.REASONING)
        s = TurnSnapshot(turns=(t0,), current_turn_index=0)
        t0_updated = t0.evolve(reasoning_text="new text")
        s = s.replace_turn(0, t0_updated)
        assert s.turns[0].reasoning_text == "new text"

    def test_frozen_immutability(self) -> None:
        s = TurnSnapshot()
        with pytest.raises(AttributeError):
            s.finished = True  # type: ignore[misc]

    def test_tool_calls_total(self) -> None:
        tp1 = ToolPhase(invocation_id="inv_1", tool_name="a")
        tp2 = ToolPhase(invocation_id="inv_2", tool_name="b")
        t0 = Turn(index=0, tool_phases=(tp1,))
        t1 = Turn(index=1, tool_phases=(tp2,))
        s = TurnSnapshot(turns=(t0, t1))
        assert s.tool_calls_total == 2

    def test_open_tool_count(self) -> None:
        tp_open = ToolPhase(invocation_id="inv_1", tool_name="a", state=ToolLifecycleState.RUNNING)
        tp_closed = ToolPhase(
            invocation_id="inv_2", tool_name="b", state=ToolLifecycleState.SUCCEEDED
        )
        t0 = Turn(index=0, tool_phases=(tp_open, tp_closed))
        s = TurnSnapshot(turns=(t0,))
        assert s.open_tool_count == 1


# ── TurnStateMachine ────────────────────────────────────────


class TestTurnStateMachine:
    def test_run_started_sets_started_at(self) -> None:
        from gateway.presentation.turn_state_machine import TurnStateMachine
        from lca.contracts.models.observability.journal import (
            AgentRunStarted,
            RunScope,
            StampedEvent,
        )

        machine = TurnStateMachine()
        stamped = StampedEvent(
            seq=1,
            ts=100.0,
            scope=RunScope(trace_id="t", run_id="r"),
            event=AgentRunStarted(objective="test", objective_preview="test"),
        )
        result = machine.build(TurnSnapshot(), stamped)
        assert result.started_at == 100.0

    def test_reasoning_delta_creates_turn(self) -> None:
        from gateway.presentation.turn_state_machine import TurnStateMachine
        from lca.contracts.models.observability.journal import (
            ReasoningDelta,
            RunScope,
            StampedEvent,
        )

        machine = TurnStateMachine()
        stamped = StampedEvent(
            seq=1,
            ts=100.0,
            scope=RunScope(trace_id="t", run_id="r"),
            event=ReasoningDelta(step=0, text_delta="Let me think", seq=0),
        )
        result = machine.build(TurnSnapshot(), stamped)
        assert len(result.turns) == 1
        assert result.turns[0].reasoning_text == "Let me think"
        assert result.turns[0].phase == PhaseKind.REASONING

    def test_multiple_reasoning_deltas_accumulate(self) -> None:
        from gateway.presentation.turn_state_machine import TurnStateMachine
        from lca.contracts.models.observability.journal import (
            ReasoningDelta,
            RunScope,
            StampedEvent,
        )

        machine = TurnStateMachine()
        scope = RunScope(trace_id="t", run_id="r")
        snap = TurnSnapshot()
        for i, text in enumerate(["Hello ", "world", "!"]):
            stamped = StampedEvent(
                seq=i + 1,
                ts=100.0 + i,
                scope=scope,
                event=ReasoningDelta(step=0, text_delta=text, seq=i),
            )
            snap = machine.build(snap, stamped)

        assert snap.turns[0].reasoning_text == "Hello world!"

    def test_run_finished_sets_steps(self) -> None:
        from gateway.presentation.turn_state_machine import TurnStateMachine
        from lca.contracts.models.observability.journal import (
            AgentRunFinished,
            RunScope,
            StampedEvent,
        )

        machine = TurnStateMachine()
        stamped = StampedEvent(
            seq=10,
            ts=200.0,
            scope=RunScope(trace_id="t", run_id="r"),
            event=AgentRunFinished(status="completed", output_text="done", steps=5),
        )
        result = machine.build(TurnSnapshot(), stamped)
        assert result.finished is True
        assert result.steps_total == 5
        assert result.status == "completed"
        assert result.final_output == "done"
