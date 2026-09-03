"""Reducer contract tests (ADR-0066).

Pure-function tests on the Reducer Protocol default implementation.
"""

from __future__ import annotations

import pytest

from lca.contracts.event import Category, EventPayload
from lca.contracts.models.core.activation import ActivatedSkill
from lca.contracts.models.core.budget import create_budget
from lca.contracts.models.core.decision import Decision, Observation, Reflection, Turn
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.perception import ContextItem, ContextManifest
from lca.contracts.models.core.state import AgentState
from lca.contracts.models.core.stop import StopDecision
from lca.runtime.reducer import DefaultReducer
from lca_kernel.events.bus import EventBus
from lca_kernel.events.mechanism import _DEFAULT_CONFIG_DIR
from lca_kernel.events.payloads_spine import SpineEventPayload
from lca_kernel.events.registry import EventRegistry


def _state() -> AgentState:
    return AgentState(
        trace_id="trace-1",
        task="t",
        budget=create_budget(max_steps=10),
    )


def test_apply_step_advanced_updates_step_and_budget() -> None:
    state = _state()
    out = DefaultReducer().apply_step_advanced(state, 3)
    assert out.step == 3
    assert out.budget.used_steps == 3


def test_apply_perception_writes_manifest_digest() -> None:
    state = _state()
    manifest = ContextManifest(
        items=(ContextItem(kind="clock", payload="12:00", provenance="clock"),), digest="abc"
    )
    out = DefaultReducer().apply_perception(state, manifest)
    assert out.extra["manifest_digest"] == "abc"


def test_apply_turn_appends_history() -> None:
    state = _state()
    decision = Decision(
        decision_id="d1",
        action_type="respond",  # type: ignore[arg-type]
        rationale="",
        confidence=1.0,
    )
    observation = Observation(observation_id="o1", success=True, payload="ok")
    reflection = Reflection(reflection_id="r1", verdict="on_track")  # type: ignore[arg-type]
    turn = Turn(decision=decision, observation=observation, reflection=reflection)
    out = DefaultReducer().apply_turn(state, turn)
    assert len(out.history) == 1
    assert out.history[0] is turn


def test_apply_activation_no_op_on_empty() -> None:
    state = _state()
    out = DefaultReducer().apply_activation(state, ())
    assert out.activated_skills == state.activated_skills


def test_apply_activation_extends_skills() -> None:
    state = _state()
    activated = (ActivatedSkill(skill_id="s1", name="S1", activated_at_step=0),)
    out = DefaultReducer().apply_activation(state, activated)
    assert out.activated_skills == [activated[0]]


def test_apply_stop_writes_status_only() -> None:
    """ADR-0158 决策 四:apply_stop 只折叠 status / last_error;final_output 由
    StopDecision 携带并由 apply_terminal_outcome 转入 TerminalOutcome.final_output_ref。

    旧 test_apply_stop_writes_status_and_output 断言 state.final_output == "done"
    已不适用(字段已删除)。
    """

    state = _state()
    stop = StopDecision(
        should_stop=True,
        reason="completed",  # type: ignore[arg-type]
        status=TaskStatus.COMPLETED,
        final_output="done",
    )
    out = DefaultReducer().apply_stop(state, stop)
    assert out.status == TaskStatus.COMPLETED
    # final_output 不在 AgentState 上;StopDecision.final_output 由
    # apply_terminal_outcome 读走,见 test_apply_terminal_outcome_uses_stop_final_output


def test_apply_stop_does_not_mutate_state_final_output_field() -> None:
    """ADR-0158 决策 四:AgentState 已无 final_output 字段;apply_stop 不再尝试写入。"""

    state = _state()
    stop = StopDecision(
        should_stop=True,
        reason="completed",  # type: ignore[arg-type]
        status=TaskStatus.COMPLETED,
        final_output="done\n\n[artifact closure]",
    )

    out = DefaultReducer().apply_stop(state, stop)
    # 既无 final_output 字段可断言;改断言 stop.final_output 透传(stop 不可变)
    assert stop.final_output == "done\n\n[artifact closure]"
    assert "final_output" not in out.__annotations__


def test_apply_error_marks_failed() -> None:
    state = _state()
    err = RuntimeError("boom")
    out = DefaultReducer().apply_error(state, err)
    assert out.status == TaskStatus.FAILED
    assert "boom" in (out.last_error or "")


def test_apply_paused_marks_input_required() -> None:
    state = _state()
    out = DefaultReducer().apply_paused(state, "snap-ref")
    assert out.status == TaskStatus.INPUT_REQUIRED


def test_apply_resume_records_input_turn_and_restores_working_status() -> None:
    state = _state()
    state.status = TaskStatus.INPUT_REQUIRED
    turn = Turn(
        decision=Decision(
            decision_id="resume-decision",
            action_type="ask_human",  # type: ignore[arg-type]
            rationale="answer received",
            confidence=1.0,
        ),
        observation=Observation(observation_id="resume-observation", success=True, payload="yes"),
    )

    out = DefaultReducer().apply_resume(state, "yes", turn)

    assert out.status == TaskStatus.WORKING
    assert out.working_memory["resume_input"] == "yes"
    assert out.history == [turn]
    assert out.step == 1


def test_apply_artifact_closure_method_is_removed() -> None:
    """ADR-0158 决策 六:apply_artifact_closure 整段删除;Reducer 不再折叠 closure。

    closure 改走 transport projection 通道(artifact_closure.py / SSE);
    reducer 仍是 state 唯一 writer(ADR-0070 C4)。
    """

    reducer = DefaultReducer()
    assert not hasattr(reducer, "apply_artifact_closure"), (
        "DefaultReducer.apply_artifact_closure 必须被删除(ADR-0158 决策 六)"
    )


def test_apply_terminal_outcome_rejects_waiting_input_without_durable_cursor() -> None:
    from lca.contracts.protocols.declarative.declarative_phase_graph import (
        DeclarativeValidationError,
    )

    stop = StopDecision(
        should_stop=True,
        reason="approval_required",  # type: ignore[arg-type]
        status=TaskStatus.INPUT_REQUIRED,
    )

    # SSOT 收口(SSOT-Teardown):apply_terminal_outcome 不再内部调 apply_stop;
    # teardown 顺序由 caller 决定——caller 必须先 apply_stop 再 apply_terminal_outcome。
    state = DefaultReducer().apply_stop(_state(), stop)
    with pytest.raises(
        DeclarativeValidationError,
        match="requires a durable resume cursor",
    ):
        DefaultReducer().apply_terminal_outcome(state, stop, plan_ref="plan-hil", journal_seq_end=4)


# ── ADR-0077 invariant: TerminalOutcome(FAILED) must always carry error_ref ──
#
# Regression gate for run_d111c5459031 / run_98ef69d5ff29 / run_697848752aa6 /
# run_27123ee235ac / run_10503d64d622 / run_93d4a69e3c14 — six runs that all
# died with ``TerminalOutcome(FAILED) requires error_ref`` because the
# upstream ``StopDecision`` carries no error string and ``state.last_error``
# was empty when the loop terminated.


class TestFailedTerminalCarriesErrorRef:
    """Pin the ADR-0077 invariant for ``kind=FAILED``.

    The reducer is the sole constructor of ``TerminalOutcome``; if it ever
    yields a FAILED outcome without ``error_ref`` the model layer raises
    ``ValueError`` mid-run, the user sees an opaque status=failed response,
    and the Journal contains no error context — exactly what run_d111c5459031
    and its siblings demonstrated.
    """

    @staticmethod
    def _state_with_empty_error() -> AgentState:
        # last_error=None is the realistic case: a StopDecision lands with
        # status=FAILED and no message (StopDecision has no error field).
        return AgentState(
            trace_id="trace-failed-no-msg",
            task="t",
            budget=create_budget(max_steps=10),
        )

    def test_failed_with_empty_state_error_still_builds_error_ref(self) -> None:
        from lca.contracts.models.core.stop import StopReason

        stop = StopDecision(
            should_stop=True,
            reason=StopReason.ERROR,
            status=TaskStatus.FAILED,
        )
        state = self._state_with_empty_error()
        # Real-world precondition: last_error stays None (StopDecision has no
        # error field; nobody wrote one before apply_terminal_outcome runs).
        assert state.last_error is None

        outcome = DefaultReducer().apply_terminal_outcome(
            state, stop, plan_ref="plan-x", journal_seq_end=2
        )

        assert outcome.kind.value == "failed"
        assert outcome.error_ref is not None
        assert outcome.error_ref.message  # non-empty fallback derived from stop reason

    def test_failed_with_explicit_state_error_preserves_message(self) -> None:
        from lca.contracts.models.core.stop import StopReason

        stop = StopDecision(
            should_stop=True,
            reason=StopReason.ERROR,
            status=TaskStatus.FAILED,
        )
        state = self._state_with_empty_error()
        state.last_error = "explicit failure: cloud-sandbox unavailable"

        outcome = DefaultReducer().apply_terminal_outcome(
            state, stop, plan_ref="plan-x", journal_seq_end=2
        )

        assert outcome.kind.value == "failed"
        assert outcome.error_ref is not None
        assert outcome.error_ref.message == "explicit failure: cloud-sandbox unavailable"


# ── _instrument_apply → EventBus(ADR-0183 PR-8) ──────────────────────────


def _make_collecting_bus() -> tuple[EventBus[EventPayload], list[EventPayload]]:
    """EventBus with the real yaml registry and a collecting subscriber.

    The collector subscribes under the ``SpineChainSink`` identity: the yaml
    subscribers whitelist of ``spine.runtime.reducer.apply`` authorizes that
    class, so the test callback passes subscribe authorization.
    """
    from lca.plugins.events.sinks.spine_chain_sink.sink import SpineChainSink

    bus: EventBus[EventPayload] = EventBus(EventRegistry.load(_DEFAULT_CONFIG_DIR))
    seen: list[EventPayload] = []
    bus.subscribe(
        plugin=SpineChainSink,
        category=Category("spine.runtime.reducer.apply"),
        on_event=lambda payload, ref: seen.append(payload),
    )
    return bus, seen


class TestInstrumentApply:
    """``_instrument_apply`` publishes ``runtime.reducer.apply`` via EventBus."""

    def test_instrument_apply_success_emits_paired_markers(self) -> None:
        """One fold emits start + end markers with the spine payload shape."""
        bus, seen = _make_collecting_bus()
        EventBus.set_default(bus)
        try:
            DefaultReducer().apply_step_advanced(_state(), 2)
        finally:
            EventBus.set_default(None)

        markers = [p for p in seen if isinstance(p, SpineEventPayload)]
        assert [m.payload for m in markers] == [
            {"method": "apply_step_advanced", "phase": "start", "run_id": ""},
            {
                "method": "apply_step_advanced",
                "phase": "end",
                "outcome": "success",
                "run_id": "",
            },
        ]
        assert all(m.category.value == "spine.runtime.reducer.apply" for m in markers)
        assert all(m.channel == "fact" for m in markers)

    def test_instrument_apply_failure_outcome_and_exception_propagate(self) -> None:
        """A raising fold emits ``outcome="failure"`` and re-raises the error."""
        from lca.contracts.protocols.declarative.declarative_phase_graph import (
            DeclarativeValidationError,
        )

        bus, seen = _make_collecting_bus()
        EventBus.set_default(bus)
        try:
            stop = StopDecision(
                should_stop=True,
                reason="approval_required",  # type: ignore[arg-type]
                status=TaskStatus.INPUT_REQUIRED,
            )
            state = DefaultReducer().apply_stop(_state(), stop)
            with pytest.raises(DeclarativeValidationError):
                DefaultReducer().apply_terminal_outcome(
                    state, stop, plan_ref="plan-x", journal_seq_end=1
                )
        finally:
            EventBus.set_default(None)

        markers = [
            p.payload
            for p in seen
            if isinstance(p, SpineEventPayload) and p.payload["method"] == "apply_terminal_outcome"
        ]
        assert [m["phase"] for m in markers] == ["start", "end"]
        assert markers[1]["outcome"] == "failure"

    def test_instrument_apply_dispatches_on_default_event_bus(self) -> None:
        """Reducer fold dispatches each ``apply_*`` mark via EventBus.publish
        to whichever bus is bound as the default singleton; an isolated bus
        instance receives nothing."""
        from lca.plugins.events.sinks.spine_chain_sink.sink import SpineChainSink

        registry = EventRegistry.load(_DEFAULT_CONFIG_DIR)
        isolated_bus = EventBus(registry)
        isolated_seen: list[EventPayload] = []
        isolated_bus.subscribe(
            plugin=SpineChainSink,
            category=Category("spine.runtime.reducer.apply"),
            on_event=lambda payload, ref: isolated_seen.append(payload),
        )
        bus, seen = _make_collecting_bus()
        EventBus.set_default(bus)
        try:
            DefaultReducer().apply_paused(_state(), "snap-ref")
        finally:
            EventBus.set_default(None)

        assert len(seen) == 2
        # 隔离实例未被 set_default,reducer 不可能路由到它
        assert isolated_seen == []
