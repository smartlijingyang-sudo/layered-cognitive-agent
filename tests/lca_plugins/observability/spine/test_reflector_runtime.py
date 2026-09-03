"""Tests for runtime spine reflector (PR-3.4).

Asserts that the runtime layer boundary methods emit the canonical
``EXECUTION_POINTS`` events when a spine is wired, and that the
emit helpers are safe no-ops when no spine is wired.

The pattern mirrors the cognition reflector test
(``test_reflector_cognition.py``): helpers read the process-local
active spine installed by ``set_active_spine`` and call
``spine.append(...)``.
"""

# ADR-0181 PR-3：旧 spine 反射器（lca.plugins.observability.spine.reflectors.runtime）
# 已迁到 lca.plugins.events.publishers.spine_reflector_runtime。EventMechanism
# 路径下等价覆盖在
# tests/plugins/events/publishers/test_spine_reflector_runtime.py。
# 删-when：PR-9 旧 spine 全部退役后，本文件删除（rg
# EventSpine lca/plugins/observability/spine/ = 0 触发）。
from __future__ import annotations

from typing import Any, ClassVar

import pytest

from lca.infrastructure.observability.spine.context import SpineContext
from lca.infrastructure.observability.spine.event_record import EventRecord
from lca.infrastructure.observability.spine.event_spine import EventSpine


pytestmark = pytest.mark.xfail(
    reason=(
        "ADR-0181 PR-3：旧 EventSpine 反射器路径已退役。runtime emit_* 等价 "
        "EventMechanism 路径覆盖在 tests/plugins/events/publishers/test_spine_reflector_runtime.py；"
        "本测试在 PR-9 旧 spine 全退役时删（rg "
        "lca.plugins.observability.spine.reflectors.runtime lca/ = 0 触发）。"
    ),
    strict=True,
)

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
    SpineContext.set_run("runtime-reflector-test")
    return spine, sink


def _eps_by_point(records: list[EventRecord]) -> dict[str, list[EventRecord]]:
    out: dict[str, list[EventRecord]] = {}
    for rec in records:
        out.setdefault(rec.execution_point, []).append(rec)
    return out


def _run(coro: Any) -> Any:
    """Run an awaitable synchronously (test helper)."""
    import asyncio

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
    return loop.run_until_complete(coro)


# ── safe no-ops without active spine ────────────────────────────────


def test_emit_helpers_are_safe_when_no_spine_wired() -> None:
    """Without an active spine, the helpers must not raise."""
    from lca.plugins.observability.spine.reflectors.runtime import (
        emit_exception_caught,
        emit_exception_finally,
        emit_runtime_checkpoint_create,
        emit_runtime_event_publisher_publish,
        emit_runtime_reducer_apply_end,
        emit_runtime_reducer_apply_start,
        emit_runtime_resume_end,
        emit_runtime_resume_start,
    )

    # All of these must complete without raising.
    emit_runtime_reducer_apply_start(method="apply_step_advanced")
    emit_runtime_reducer_apply_end(method="apply_step_advanced", outcome="success")
    emit_runtime_checkpoint_create(plan_ref="p", state_ref="s", node_id="n")
    emit_runtime_resume_start(plan_ref="p", state_ref="s", node_id="n")
    emit_runtime_resume_end(plan_ref="p", state_ref="s", node_id="n", outcome="success")
    emit_runtime_event_publisher_publish(event_type="STARTED", trace_id="t")
    emit_exception_caught(boundary="resume", exc_type="ValueError", message="x")
    emit_exception_finally(boundary="resume")


# ── helpers forward to active spine ──────────────────────────────────


def test_reducer_apply_helpers_forward_to_active_spine() -> None:
    """emit_runtime_reducer_apply_start/end forward to the active spine."""
    from lca.plugins.observability.spine.reflectors.runtime import (
        emit_runtime_reducer_apply_end,
        emit_runtime_reducer_apply_start,
        set_active_spine,
    )

    spine, sink = _make_spine()
    set_active_spine(spine)
    try:
        emit_runtime_reducer_apply_start(method="apply_step_advanced")
        emit_runtime_reducer_apply_end(method="apply_step_advanced", outcome="success")
    finally:
        set_active_spine(None)

    points = [r.execution_point for r in sink.records]
    assert points == ["runtime.reducer.apply", "runtime.reducer.apply"]
    assert sink.records[0].payload["phase"] == "start"
    assert sink.records[1].payload["phase"] == "end"
    assert sink.records[1].outcome == "success"
    assert sink.records[0].payload["method"] == "apply_step_advanced"


def test_checkpoint_create_helper_forward_to_active_spine() -> None:
    """emit_runtime_checkpoint_create forwards with payload."""
    from lca.plugins.observability.spine.reflectors.runtime import (
        emit_runtime_checkpoint_create,
        set_active_spine,
    )

    spine, sink = _make_spine()
    set_active_spine(spine)
    try:
        emit_runtime_checkpoint_create(plan_ref="plan-x", state_ref="mem://1/0", node_id="n1")
    finally:
        set_active_spine(None)

    assert len(sink.records) == 1
    rec = sink.records[0]
    assert rec.execution_point == "runtime.checkpoint.create"
    assert rec.payload["plan_ref"] == "plan-x"
    assert rec.payload["state_ref"] == "mem://1/0"
    assert rec.payload["node_id"] == "n1"
    assert rec.outcome == "success"


def test_resume_helpers_forward_to_active_spine() -> None:
    """emit_runtime_resume_start/end forward as a start/end pair."""
    from lca.plugins.observability.spine.reflectors.runtime import (
        emit_runtime_resume_end,
        emit_runtime_resume_start,
        set_active_spine,
    )

    spine, sink = _make_spine()
    set_active_spine(spine)
    try:
        emit_runtime_resume_start(plan_ref="p", state_ref="s", node_id="n")
        emit_runtime_resume_end(plan_ref="p", state_ref="s", node_id="n", outcome="success")
    finally:
        set_active_spine(None)

    points = [r.execution_point for r in sink.records]
    assert points == ["runtime.resume.start", "runtime.resume.end"]
    assert sink.records[1].outcome == "success"


def test_event_publisher_publish_helper_forwards() -> None:
    """emit_runtime_event_publisher_publish forwards per-publish."""
    from lca.plugins.observability.spine.reflectors.runtime import (
        emit_runtime_event_publisher_publish,
        set_active_spine,
    )

    spine, sink = _make_spine()
    set_active_spine(spine)
    try:
        emit_runtime_event_publisher_publish(event_type="STARTED", trace_id="t1")
        emit_runtime_event_publisher_publish(event_type="COMPLETED", trace_id="t1")
    finally:
        set_active_spine(None)

    assert [r.execution_point for r in sink.records] == [
        "runtime.event_publisher.publish",
        "runtime.event_publisher.publish",
    ]
    assert sink.records[0].payload["event_type"] == "STARTED"
    assert sink.records[1].payload["event_type"] == "COMPLETED"


def test_exception_caught_finally_helpers_forward() -> None:
    """exception.caught + exception.finally form a diagnostic pair."""
    from lca.plugins.observability.spine.reflectors.runtime import (
        emit_exception_caught,
        emit_exception_finally,
        set_active_spine,
    )

    spine, sink = _make_spine()
    set_active_spine(spine)
    try:
        emit_exception_caught(
            boundary="resume",
            exc_type="ValueError",
            message="resume failed",
            trace_id="t1",
        )
        emit_exception_finally(boundary="resume", trace_id="t1")
    finally:
        set_active_spine(None)

    points = [r.execution_point for r in sink.records]
    assert points == ["exception.caught", "exception.finally"]
    assert sink.records[0].outcome == "failure"
    assert sink.records[0].payload["boundary"] == "resume"
    assert sink.records[0].payload["exc_type"] == "ValueError"


# ── reducer.apply_* methods emit runtime.reducer.apply (middleware) ──


def test_default_reducer_apply_methods_emit_reducer_apply_events() -> None:
    """DefaultReducer.apply_* methods emit runtime.reducer.apply start/end."""
    from lca.contracts.models.core.budget import create_budget
    from lca.contracts.models.core.state import AgentState
    from lca.plugins.observability.spine.reflectors.runtime import set_active_spine
    from lca.runtime.reducer import DefaultReducer

    spine, sink = _make_spine()
    set_active_spine(spine)
    try:
        state = AgentState(
            trace_id="trace-1",
            task="t",
            budget=create_budget(max_steps=10),
        )
        DefaultReducer().apply_step_advanced(state, 3)
    finally:
        set_active_spine(None)

    by_point = _eps_by_point(sink.records)
    recs = by_point["runtime.reducer.apply"]
    assert len(recs) == 2
    assert recs[0].payload["phase"] == "start"
    assert recs[1].payload["phase"] == "end"
    assert recs[0].payload["method"] == "apply_step_advanced"
    assert recs[1].outcome == "success"


def test_default_reducer_emits_apply_events_for_all_apply_methods() -> None:
    """Every public apply_* method on DefaultReducer emits start/end."""
    from lca.contracts.models.core.budget import create_budget
    from lca.contracts.models.core.lifecycle import TaskStatus
    from lca.contracts.models.core.state import AgentState
    from lca.contracts.models.core.stop import StopDecision
    from lca.plugins.observability.spine.reflectors.runtime import set_active_spine
    from lca.runtime.reducer import DefaultReducer

    spine, sink = _make_spine()
    set_active_spine(spine)
    try:
        reducer = DefaultReducer()
        state = AgentState(
            trace_id="trace-1",
            task="t",
            budget=create_budget(max_steps=10),
        )
        # Exercise at least three different apply_* entry points.
        reducer.apply_step_advanced(state, 2)
        reducer.apply_resume(state, input_value=None, turn=None)
        reducer.apply_error(state, RuntimeError("x"))
        stop = StopDecision(
            should_stop=True,
            reason="completed",  # type: ignore[arg-type]
            status=TaskStatus.COMPLETED,
        )
        reducer.apply_stop(state, stop)
    finally:
        set_active_spine(None)

    by_method: dict[str, list[str]] = {}
    for rec in sink.records:
        by_method.setdefault(rec.payload["method"], []).append(rec.payload["phase"])
    assert by_method.get("apply_step_advanced") == ["start", "end"]
    assert by_method.get("apply_resume") == ["start", "end"]
    assert by_method.get("apply_error") == ["start", "end"]
    assert by_method.get("apply_stop") == ["start", "end"]


def test_default_reducer_apply_failure_end_event_on_exception() -> None:
    """If an apply_* method raises, the spine still receives end with outcome=failure."""
    from lca.contracts.models.core.budget import create_budget
    from lca.contracts.models.core.state import AgentState
    from lca.plugins.observability.spine.reflectors.runtime import set_active_spine

    spine, sink = _make_spine()
    set_active_spine(spine)
    try:
        reducer = _ExplodingReducer()
        state = AgentState(
            trace_id="trace-1",
            task="t",
            budget=create_budget(max_steps=10),
        )
        import pytest

        with pytest.raises(RuntimeError, match="apply boom"):
            reducer.apply_step_advanced(state, 0)
    finally:
        set_active_spine(None)

    recs = [r for r in sink.records if r.execution_point == "runtime.reducer.apply"]
    assert len(recs) == 2
    assert recs[0].payload["phase"] == "start"
    assert recs[1].payload["phase"] == "end"
    assert recs[1].outcome == "failure"


class _ExplodingReducer:
    """Stand-in for a Reducer whose apply_step_advanced raises.

    We don't subclass DefaultReducer because its apply_* methods are
    pure; we wrap one to simulate a misbehaving implementation that the
    middleware must still wrap.
    """

    name = "exploding"

    def apply_step_advanced(self, state: Any, step: int) -> Any:
        from lca.plugins.observability.spine.reflectors.runtime import (
            emit_runtime_reducer_apply_end,
            emit_runtime_reducer_apply_start,
        )

        emit_runtime_reducer_apply_start(method="apply_step_advanced")
        try:
            raise RuntimeError("apply boom")
        finally:
            emit_runtime_reducer_apply_end(method="apply_step_advanced", outcome="failure")


# ── checkpoint creation emits runtime.checkpoint.create ──────────────


def test_declarative_checkpoint_construction_emits_checkpoint_create() -> None:
    """Constructing a DeclarativeCheckpoint emits runtime.checkpoint.create."""
    from lca.contracts.models.core.state import StateSnapshot
    from lca.contracts.protocols.declarative.declarative_phase_graph import PhaseRunCursor
    from lca.plugins.observability.spine.reflectors.runtime import set_active_spine
    from lca.runtime.checkpoint_resolution import DeclarativeCheckpoint

    spine, sink = _make_spine()
    set_active_spine(spine)
    try:
        snapshot = StateSnapshot(
            snapshot_id="snap-1",
            step=0,
            state_ref="mem://1/0",
        )
        cursor = PhaseRunCursor(
            plan_ref="plan-x",
            node_id="node-1",
            visit_counts=(),
            edge_counts=(),
            artifacts={},
            causation_refs=(),
            budget_snapshot={},
        )
        DeclarativeCheckpoint(
            state_snapshot=snapshot,
            cursor=cursor,
            plan_ref="plan-x",
        )
    finally:
        set_active_spine(None)

    recs = [r for r in sink.records if r.execution_point == "runtime.checkpoint.create"]
    assert len(recs) == 1
    assert recs[0].payload["plan_ref"] == "plan-x"
    assert recs[0].payload["state_ref"] == "mem://1/0"
    assert recs[0].payload["node_id"] == "node-1"
    assert recs[0].outcome == "success"


# ── runtime_lifecycle_emitter.publish emits runtime.event_publisher.publish ──


def test_runtime_lifecycle_emitter_publish_emits_event_publisher_event() -> None:
    """RuntimeLifecycleEmitter.publish emits runtime.event_publisher.publish."""
    from lca.contracts.models.core.budget import create_budget
    from lca.contracts.models.core.lifecycle import TaskStatus
    from lca.contracts.models.core.state import AgentState
    from lca.contracts.protocols.runtime.runtime_lifecycle import (
        RuntimeLifecycleEventType,
    )
    from lca.plugins.observability.spine.reflectors.runtime import set_active_spine

    spine, sink = _make_spine()
    set_active_spine(spine)
    try:
        emitter = _make_lifecycle_emitter()
        state = AgentState(
            trace_id="t1",
            task="x",
            budget=create_budget(max_steps=5),
            status=TaskStatus.WORKING,
        )
        _run(emitter.publish(RuntimeLifecycleEventType.STARTED, state))
    finally:
        set_active_spine(None)

    recs = [r for r in sink.records if r.execution_point == "runtime.event_publisher.publish"]
    assert len(recs) == 1
    assert recs[0].payload["event_type"] == "started"
    assert recs[0].payload["trace_id"] == "t1"


def _make_lifecycle_emitter() -> Any:
    """Build a RuntimeLifecycleEmitter with stub bindings + spine wired."""
    from lca.runtime.runtime_lifecycle_emitter import RuntimeLifecycleEmitter

    class _StubBindings:
        def plan_ref(self) -> str:
            return "plan-x"

        lifecycle_publisher = _FakeLifecyclePublisher()

    return RuntimeLifecycleEmitter(_StubBindings())  # type: ignore[arg-type]


class _FakeLifecyclePublisher:
    """Captures the event but does not forward it anywhere."""

    async def publish(self, event: Any) -> None:
        del event


# ── CognitiveRuntime._run_driver envelope: resume + exception ───────


class _StubDriver:
    """Async runner that completes a turn by returning a Result stub."""

    def __init__(self, *, raise_exc: BaseException | None = None) -> None:
        self._raise = raise_exc

    async def resume(self, checkpoint: Any) -> Any:
        from lca.contracts.models.core.budget import Budget
        from lca.contracts.models.core.lifecycle import TaskStatus
        from lca.contracts.models.core.result import Result

        if self._raise is not None:
            raise self._raise
        return Result(
            trace_id="t1",
            status=TaskStatus.COMPLETED,
            final_state_ref="mem://1/0",
            total_steps=1,
            budget_used=Budget(),
            output="ok",
            lessons=[],
        )


class _StubBindings:
    """Minimal DeclarativeRuntimeBindings surface for the envelope path."""

    plan = None
    phase_executors: ClassVar[dict[str, Any]] = {}

    def __init__(self, *, driver: _StubDriver) -> None:
        self._driver = driver
        from lca.contracts.models.core.budget import DEFAULT_MAX_STEPS
        from lca.contracts.models.core.state import AgentState
        from lca.contracts.protocols.session.resume_input import ResumeInputAdapter

        class _NoopStateStore:
            async def load(self, ref: str) -> Any:
                return AgentState(
                    trace_id="t1",
                    task="x",
                    budget=None,
                )

            async def save(self, state: Any, ref: str = "") -> str:
                return ref or "mem://1/0"

        class _NoopResumeInputAdapter(ResumeInputAdapter):
            def normalize(self, value: Any) -> Any:
                from dataclasses import dataclass

                @dataclass
                class _Norm:
                    input_value: Any = None
                    turn: Any = None

                return _Norm()

        self._state_store = _NoopStateStore()
        self.state_store = self._state_store
        self._resume_input_adapter = _NoopResumeInputAdapter()
        self.resume_input_adapter = self._resume_input_adapter
        # The reducer used inside CognitiveRuntime.resume
        from lca.runtime.reducer import DefaultReducer

        self.reducer = DefaultReducer()
        self.lifecycle_publisher = _FakeLifecyclePublisher()
        # Other unused attributes referenced via properties
        self.capabilities = type(
            "C", (), {"brain": None, "body": None, "memory": None, "perceive_hub": None}
        )()
        self._hooks = type(
            "H",
            (),
            {"trigger": lambda self, *a, **kw: _noop_awaitable()},
        )()
        self._state_store_obj = self._state_store
        self.DEFAULT_MAX_STEPS = DEFAULT_MAX_STEPS

    def require_executable_plan(self) -> Any:
        return None  # no-op for the stub envelope path

    def plan_ref(self) -> str:
        return "plan-x"

    def new_driver(self) -> _StubDriver:
        return self._driver


def _noop_awaitable() -> Any:
    """Return a coroutine that yields None — used as a stub hook trigger."""

    async def _coro() -> None:
        return None

    return _coro()


def test_cognitive_runtime_run_driver_emits_resume_start_end_on_success() -> None:
    """A successful resume turn emits runtime.resume.start + runtime.resume.end."""
    from lca.contracts.models.core.state import StateSnapshot
    from lca.contracts.protocols.declarative.declarative_phase_graph import PhaseRunCursor
    from lca.plugins.observability.spine.reflectors.runtime import set_active_spine
    from lca.runtime.runtime_loop import CognitiveRuntime

    # Patch _run_driver's path: we directly drive the envelope by faking the
    # surrounding resume() flow. We test the envelope semantics with a
    # minimal CognitiveRuntime constructed via __new__.
    driver = _StubDriver()
    bindings = _StubBindings(driver=driver)
    runtime = CognitiveRuntime.__new__(CognitiveRuntime)
    runtime._bindings = bindings  # type: ignore[attr-defined]
    from lca.runtime.runtime_lifecycle_emitter import RuntimeLifecycleEmitter

    runtime._lifecycle = RuntimeLifecycleEmitter(bindings)  # type: ignore[attr-defined]

    snapshot = StateSnapshot(
        snapshot_id="snap-1",
        step=0,
        state_ref="mem://1/0",
        phase_cursor=PhaseRunCursor(
            plan_ref="plan-x",
            node_id="node-1",
            visit_counts=(),
            edge_counts=(),
            artifacts={},
            causation_refs=(),
            budget_snapshot={},
        ),
    )

    spine, sink = _make_spine()
    set_active_spine(spine)
    try:
        _run(runtime.resume(snapshot))
    finally:
        set_active_spine(None)

    starts = [r for r in sink.records if r.execution_point == "runtime.resume.start"]
    ends = [r for r in sink.records if r.execution_point == "runtime.resume.end"]
    assert len(starts) == 1
    assert len(ends) == 1
    assert ends[0].outcome == "success"
    assert starts[0].payload["plan_ref"] == "plan-x"
    assert starts[0].payload["node_id"] == "node-1"


def test_cognitive_runtime_run_driver_emits_exception_events() -> None:
    """A failing resume turn emits exception.caught + exception.finally."""
    from lca.contracts.models.core.state import StateSnapshot
    from lca.contracts.protocols.declarative.declarative_phase_graph import PhaseRunCursor
    from lca.plugins.observability.spine.reflectors.runtime import set_active_spine
    from lca.runtime.runtime_loop import CognitiveRuntime

    driver = _StubDriver(raise_exc=RuntimeError("driver boom"))
    bindings = _StubBindings(driver=driver)
    runtime = CognitiveRuntime.__new__(CognitiveRuntime)
    runtime._bindings = bindings  # type: ignore[attr-defined]
    from lca.runtime.runtime_lifecycle_emitter import RuntimeLifecycleEmitter

    runtime._lifecycle = RuntimeLifecycleEmitter(bindings)  # type: ignore[attr-defined]

    snapshot = StateSnapshot(
        snapshot_id="snap-1",
        step=0,
        state_ref="mem://1/0",
        phase_cursor=PhaseRunCursor(
            plan_ref="plan-x",
            node_id="node-1",
            visit_counts=(),
            edge_counts=(),
            artifacts={},
            causation_refs=(),
            budget_snapshot={},
        ),
    )

    spine, sink = _make_spine()
    set_active_spine(spine)
    try:
        import pytest

        with pytest.raises(RuntimeError, match="driver boom"):
            _run(runtime.resume(snapshot))
    finally:
        set_active_spine(None)

    caught = [r for r in sink.records if r.execution_point == "exception.caught"]
    finallys = [r for r in sink.records if r.execution_point == "exception.finally"]
    assert len(caught) == 1
    assert len(finallys) == 1
    assert caught[0].payload["boundary"] == "resume"
    assert caught[0].payload["exc_type"] == "RuntimeError"
    assert "driver boom" in caught[0].payload["message"]
    # Resume end event must still fire on the failure path with outcome=failure.
    ends = [r for r in sink.records if r.execution_point == "runtime.resume.end"]
    assert len(ends) == 1
    assert ends[0].outcome == "failure"


# ── Task 7.3: ``RuntimeFieldProducer`` FieldProducer plugin ─────────
#
# Mirrors the surface contract pins in ``test_reflector_signature.py``:
# the runtime FieldProducer MUST inject the five audit-grade keys per
# call's post-phase (``return_value_fingerprint``, ``duration_ms``,
# ``input_fingerprint``, ``when_corrected``, ``prev_event_hash``).


def test_runtime_field_producer_satisfies_field_producer_protocol() -> None:
    """``RuntimeFieldProducer`` structurally implements ``FieldProducer``."""
    from lca.contracts.observability.spine.producer import FieldProducer
    from lca.plugins.observability.spine.reflectors.runtime import (
        RuntimeFieldProducer,
    )

    producer = RuntimeFieldProducer()
    assert isinstance(producer, FieldProducer)


def test_runtime_field_producer_metadata() -> None:
    """Name / priority / enabled seam attrs match the runtime reflector id."""
    from lca.plugins.observability.spine.reflectors.runtime import (
        RuntimeFieldProducer,
    )

    producer = RuntimeFieldProducer()
    assert producer.name == "spine.reflector.runtime"
    assert isinstance(producer.priority, int)
    assert producer.enabled is True


def test_produce_post_phase_returns_required_keys() -> None:
    """``produce(phase="post")`` MUST include the five documented keys."""
    from lca.plugins.observability.spine.reflectors.runtime import (
        RuntimeFieldProducer,
    )

    producer = RuntimeFieldProducer()

    def _example(a: int, b: str = "x") -> int:
        return a + len(b)

    payload = producer.produce(
        fn=_example,
        args=(1,),
        kwargs={"b": "hi"},
        ctx=None,
        span=None,
        phase="post",
    )

    assert isinstance(payload, dict)
    assert "return_value_fingerprint" in payload
    assert "duration_ms" in payload
    assert "input_fingerprint" in payload
    assert "when_corrected" in payload
    assert "prev_event_hash" in payload


def test_produce_other_phase_returns_empty_dict() -> None:
    """``produce(phase="pre")`` / ``"exception"`` contribute no fields.

    The runtime FieldProducer is a post-phase-only seam: timing,
    return-value fingerprinting, and prev-hash chaining are end-of-call
    concerns. Pre/exception phases return ``{}`` so other producers
    own those slots.
    """
    from lca.plugins.observability.spine.reflectors.runtime import (
        RuntimeFieldProducer,
    )

    producer = RuntimeFieldProducer()

    pre_payload = producer.produce(
        fn=lambda: None,
        args=(),
        kwargs={},
        ctx=None,
        span=None,
        phase="pre",
    )
    exc_payload = producer.produce(
        fn=lambda: None,
        args=(),
        kwargs={},
        ctx=None,
        span=None,
        phase="exception",
    )

    assert pre_payload == {}
    assert exc_payload == {}


def test_duration_ms_is_non_negative_number() -> None:
    """``duration_ms`` MUST be a number and non-negative."""
    from lca.plugins.observability.spine.reflectors.runtime import (
        RuntimeFieldProducer,
    )

    producer = RuntimeFieldProducer()

    def _example() -> int:
        return 42

    payload = producer.produce(
        fn=_example,
        args=(),
        kwargs={},
        ctx=None,
        span=None,
        phase="post",
    )

    duration = payload["duration_ms"]
    assert isinstance(duration, (int, float))
    assert duration >= 0


def test_return_value_fingerprint_is_sha256_hex() -> None:
    """``return_value_fingerprint`` MUST be a 64-char hex sha256 string."""
    from lca.plugins.observability.spine.reflectors.runtime import (
        RuntimeFieldProducer,
    )

    producer = RuntimeFieldProducer()

    def _example() -> str:
        return "ok"

    payload = producer.produce(
        fn=_example,
        args=(),
        kwargs={},
        ctx=None,
        span=None,
        phase="post",
    )

    fingerprint = payload["return_value_fingerprint"]
    assert isinstance(fingerprint, str)
    assert len(fingerprint) == 64
    int(fingerprint, 16)  # parseable hex


def test_input_fingerprint_is_sha256_hex() -> None:
    """``input_fingerprint`` MUST be a 64-char hex sha256 string."""
    from lca.plugins.observability.spine.reflectors.runtime import (
        RuntimeFieldProducer,
    )

    producer = RuntimeFieldProducer()

    def _example(a: int, b: str = "x") -> int:
        return a + len(b)

    payload = producer.produce(
        fn=_example,
        args=(1,),
        kwargs={"b": "hi"},
        ctx=None,
        span=None,
        phase="post",
    )

    fingerprint = payload["input_fingerprint"]
    assert isinstance(fingerprint, str)
    assert len(fingerprint) == 64
    int(fingerprint, 16)


def test_when_corrected_is_datetime_or_none() -> None:
    """``when_corrected`` MUST be a ``datetime`` (NTP-corrected timestamp)."""
    from datetime import datetime

    from lca.plugins.observability.spine.reflectors.runtime import (
        RuntimeFieldProducer,
    )

    producer = RuntimeFieldProducer()

    payload = producer.produce(
        fn=lambda: None,
        args=(),
        kwargs={},
        ctx=None,
        span=None,
        phase="post",
    )

    assert isinstance(payload["when_corrected"], datetime)


def test_prev_event_hash_reads_from_spine_context() -> None:
    """``prev_event_hash`` MUST echo the active ``SpineContext.last_hash()``.

    When no spine has been wired into the process-local ContextVar,
    ``SpineContext.last_hash()`` returns ``None``; the producer mirrors
    that as the payload value so downstream consumers always observe a
    well-formed optional string.
    """
    from lca.infrastructure.observability.spine.context import SpineContext
    from lca.plugins.observability.spine.reflectors.runtime import (
        RuntimeFieldProducer,
    )

    producer = RuntimeFieldProducer()

    # No prior event in the chain → None
    prior = SpineContext.last_hash()
    payload_none = producer.produce(
        fn=lambda: None,
        args=(),
        kwargs={},
        ctx=None,
        span=None,
        phase="post",
    )
    assert payload_none["prev_event_hash"] == prior

    # Seed the chain → producer reads the seeded value
    seeded = "sha256:abc123"
    SpineContext.chain_hash(seeded)
    try:
        payload_seeded = producer.produce(
            fn=lambda: None,
            args=(),
            kwargs={},
            ctx=None,
            span=None,
            phase="post",
        )
        assert payload_seeded["prev_event_hash"] == seeded
    finally:
        SpineContext.chain_hash(None)


def test_pre_then_post_pair_measures_duration() -> None:
    """A ``pre`` then ``post`` pair MUST yield ``duration_ms >= 0``.

    The producer maintains instance state keyed by ``id(fn)`` so a
    ``pre`` call snapshots ``time.monotonic()`` and a matching ``post``
    call computes the elapsed delta. When the post call has no
    matching pre (the test's first post call above), ``duration_ms``
    collapses to ``0.0`` rather than raise.
    """
    import time

    from lca.plugins.observability.spine.reflectors.runtime import (
        RuntimeFieldProducer,
    )

    producer = RuntimeFieldProducer()

    def _example() -> int:
        return 0

    producer.produce(
        fn=_example,
        args=(),
        kwargs={},
        ctx=None,
        span=None,
        phase="pre",
    )
    # Sleep so the monotonic diff is observably > 0 even on CI clocks.
    time.sleep(0.001)
    payload = producer.produce(
        fn=_example,
        args=(),
        kwargs={},
        ctx=None,
        span=None,
        phase="post",
    )

    duration = payload["duration_ms"]
    assert isinstance(duration, (int, float))
    assert duration >= 0


def test_plugin_manifest_declares_expected_metadata() -> None:
    """The wrapped plugin exposes the canonical id / layer / kind / provides."""
    from lca.harness.plugin_declaration import definition_from_plugin
    from lca.plugins.observability.spine import reflectors

    # Touching the module forces the @plugin decorator to attach
    # ``_lca_definition`` onto the carrier.
    assert hasattr(reflectors.runtime, "setup")

    definition = definition_from_plugin(reflectors.runtime.setup, module=__name__)
    assert definition.id == "spine.reflector.runtime"
    assert definition.spec.layer == "L0"
    assert definition.provided_capability_keys == ("field_producer.runtime",)


def test_module_export_surface() -> None:
    """The module exposes ``RuntimeFieldProducer`` in its public surface."""
    import lca.plugins.observability.spine.reflectors.runtime as runtime_module

    assert hasattr(runtime_module, "RuntimeFieldProducer")
    assert "RuntimeFieldProducer" in runtime_module.__all__
