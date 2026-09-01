"""Tests for I17 schema enforcement in ``EmitPipeline.emit`` (Task 9.2).

I17 (ADR-0165.1 §96) requires every ``*.start`` event to carry a
``source_location`` field. The check is enforced at emit time inside
``EmitPipeline.emit`` so a misconfigured pipeline cannot silently
append a non-compliant ``EventRecord`` to the spine. The
implementation lives in ``lca.plugins.observability.spine.emit_pipeline``;
this module pins the contract from the outside.

SourceAttacher (Task 9.1) is the intended producer of ``source_location``.
While Task 9.1 is still in flight this module does NOT depend on
``spine.reflector.source`` — a hand-rolled stub FieldProducer stands in
for the positive case so the I17 enforcement test is self-contained.
"""

from __future__ import annotations

from typing import Any

import pytest

from lca.infrastructure.observability.spine.context import SpanContext, SpineContext
from lca.infrastructure.observability.spine.event_record import EventRecord
from lca.infrastructure.observability.spine.event_spine import EventSpine

# ── helpers ──────────────────────────────────────────────────────────


class _CaptureSink:
    """Minimal ``EventSink`` capturing every ``EventRecord`` it sees."""

    def __init__(self) -> None:
        self.records: list[EventRecord] = []

    def write(self, record: EventRecord) -> None:
        self.records.append(record)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass


def _make_spine() -> EventSpine:
    """Return a fresh ``EventSpine`` with a capture sink and a run id wired."""
    SpineContext.set_run("i17-test")
    return EventSpine(sinks=[_CaptureSink()])


def _make_span() -> SpanContext:
    """Return a ``SpanContext`` suitable for emitting a ``brain.think.start`` event."""
    return SpanContext(
        execution_point="brain.think.start",
        span_id="lca-span-i17-0001",
        parent_span_id=None,
    )


class _StubAnomaly:
    """No-op anomaly detector — emits must not trigger detector logic here."""

    def __init__(self) -> None:
        self.calls: list[EventRecord] = []

    def on_event(self, event: EventRecord) -> None:
        self.calls.append(event)


def _stub_source_attacher() -> Any:
    """Return a FieldProducer that injects ``source_location`` for ``*.start``.

    Mirrors the SourceAttacher (Task 9.1) payload shape — ``source_location``
    with ``file`` / ``line`` / ``function`` — so the positive case here
    validates the I17 enforcement contract independently of Task 9.1.
    """

    class _StubProducer:
        name = "spine.reflector.source.stub"
        priority = 8
        enabled = True

        def produce(
            self,
            *,
            fn: Any,
            args: tuple[Any, ...],
            kwargs: dict[str, Any],
            ctx: Any,
            span: Any,
            phase: str,
        ) -> dict[str, Any]:
            del fn, args, kwargs, ctx, span, phase
            return {
                "source_location": {
                    "file": "stub.py",
                    "line": 1,
                    "function": "stub",
                },
                "call_frames": [],
                "locals_snapshot": {"pre_call": {}},
            }

    return _StubProducer()


# ── negative: *.start without source_location ────────────────────────


def test_i17_rejects_event_without_source() -> None:
    """A ``*.start`` event without ``source_location`` MUST raise ``I17Violation``."""
    from lca.plugins.observability.spine.emit_pipeline import (
        EmitPipeline,
        I17Violation,
    )

    pipeline = EmitPipeline(producers=[], anomaly=_StubAnomaly())
    spine = _make_spine()

    with pytest.raises(I17Violation) as excinfo:
        pipeline.emit(
            execution_point="brain.think.start",
            channel="fact",
            span_ctx=_make_span(),
            caller_payload={},
            spine=spine,
        )

    # The exception message MUST name the missing field and the
    # offending execution_point so logs can be triaged.
    message = str(excinfo.value)
    assert "source_location" in message
    assert "brain.think.start" in message


def test_i17_rejects_even_when_other_fields_present() -> None:
    """A ``*.start`` event missing ``source_location`` MUST raise, regardless of other fields."""
    from lca.plugins.observability.spine.emit_pipeline import (
        EmitPipeline,
        I17Violation,
    )

    pipeline = EmitPipeline(producers=[], anomaly=_StubAnomaly())
    spine = _make_spine()

    with pytest.raises(I17Violation):
        pipeline.emit(
            execution_point="brain.perceive.start",
            channel="fact",
            span_ctx=_make_span(),
            caller_payload={"call_frames": [], "locals_snapshot": {"pre_call": {}}},
            spine=spine,
        )


# ── positive: stub SourceAttacher supplies source_location ───────────


def test_i17_accepts_event_with_source_location_from_producer() -> None:
    """A ``*.start`` event with a SourceAttacher-style producer MUST emit successfully."""
    from lca.plugins.observability.spine.emit_pipeline import EmitPipeline

    producer = _stub_source_attacher()
    pipeline = EmitPipeline(producers=[producer], anomaly=_StubAnomaly())
    spine = _make_spine()

    record = pipeline.emit(
        execution_point="brain.think.start",
        channel="fact",
        span_ctx=_make_span(),
        caller_payload={},
        spine=spine,
    )

    assert isinstance(record, EventRecord)
    assert record.execution_point == "brain.think.start"
    assert record.payload["source_location"] == {
        "file": "stub.py",
        "line": 1,
        "function": "stub",
    }


def test_i17_accepts_caller_supplied_source_location() -> None:
    """``caller_payload`` carrying ``source_location`` MUST satisfy I17."""
    from lca.plugins.observability.spine.emit_pipeline import EmitPipeline

    pipeline = EmitPipeline(producers=[], anomaly=_StubAnomaly())
    spine = _make_spine()

    record = pipeline.emit(
        execution_point="brain.think.start",
        channel="fact",
        span_ctx=_make_span(),
        caller_payload={
            "source_location": {
                "file": "caller.py",
                "line": 42,
                "function": "do_thing",
            }
        },
        spine=spine,
    )

    assert record.payload["source_location"]["file"] == "caller.py"


# ── sanity: *.end does not require source_location ───────────────────


def test_i17_does_not_apply_to_end_events() -> None:
    """I17 MUST NOT fire for ``*.end`` events — only ``*.start`` is in scope."""
    from lca.plugins.observability.spine.emit_pipeline import EmitPipeline

    pipeline = EmitPipeline(producers=[], anomaly=_StubAnomaly())
    spine = _make_spine()

    record = pipeline.emit(
        execution_point="brain.think.end",
        channel="fact",
        span_ctx=_make_span(),
        caller_payload={},
        spine=spine,
    )

    assert record.execution_point == "brain.think.end"
    assert "source_location" not in record.payload


def test_i17_does_not_apply_to_non_start_non_end_events() -> None:
    """I17 MUST NOT fire for points without a ``.start``/``.end`` suffix."""
    from lca.plugins.observability.spine.emit_pipeline import EmitPipeline

    pipeline = EmitPipeline(producers=[], anomaly=_StubAnomaly())
    spine = _make_spine()

    record = pipeline.emit(
        execution_point="synthesizer.merge",
        channel="fact",
        span_ctx=_make_span(),
        caller_payload={},
        spine=spine,
    )

    assert record.execution_point == "synthesizer.merge"


# ── module surface ───────────────────────────────────────────────────


def test_i17_violation_is_exported() -> None:
    """``I17Violation`` MUST be part of the public surface of emit_pipeline."""
    import lca.plugins.observability.spine.emit_pipeline as emit_pipeline_module

    assert hasattr(emit_pipeline_module, "I17Violation")
    assert "I17Violation" in emit_pipeline_module.__all__
