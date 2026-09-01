"""Tests for the ``spine.emit_pipeline`` plugin (Task 7.8).

The emit pipeline is the assembly-line for ``EventRecord`` payloads
(ADR-0165 / ADR-0165.1 §7.5.7). For each emit it:

1. Sorts enabled ``FieldProducer`` plugins by ``priority`` (ascending;
   lower numbers run earlier).
2. Calls each producer's ``produce(phase="pre", ...)`` and merges the
   returned dicts in priority order. Later priorities overwrite
   earlier ones on key conflict — the documented override direction
   (see module docstring).
3. Creates the ``EventRecord`` via ``EventSpine.append`` so
   ``EventRecord`` enforces I12 (close-set ``execution_point``,
   ``channel``, ``outcome``, ``phase``).
4. Runs the bound ``AnomalyDetector.on_event`` (best-effort) so the
   I15 8-detector sweep sees every emitted record after it is sealed.

These tests pin the three documented behaviours:

- three producers merge in priority order without overlap
- the anomaly detector is called exactly once per emit
- a producer raising does not stop the pipeline (remaining producers
  still run; the record is still appended; the detector still fires)
"""

from __future__ import annotations

from typing import Any

from lca.contracts.observability.spine.producer import FieldProducer
from lca.infrastructure.observability.spine.context import SpanContext, SpineContext
from lca.infrastructure.observability.spine.event_record import EventRecord
from lca.infrastructure.observability.spine.event_spine import EventSpine
from lca.infrastructure.observability.spine.manifest import EXECUTION_POINTS
from lca.infrastructure.observability.spine.sinks.base import EventSink

# ── helpers ──────────────────────────────────────────────────────────


class _CaptureSink:
    """Minimal ``EventSink`` that records every ``EventRecord`` in order."""

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
    SpineContext.set_run("emit-pipeline-test")
    return EventSpine(sinks=[_CaptureSink()])


def _make_span() -> SpanContext:
    """Return a ``SpanContext`` suitable for an emit pipeline call."""
    return SpanContext(
        execution_point="brain.perceive.start",
        span_id="lca-span-00000001",
        parent_span_id=None,
    )


def _failing_producer(name: str, priority: int) -> FieldProducer:
    """Return a producer whose ``produce`` always raises ``RuntimeError``."""

    class _BoomProducer:
        pass

    p = _BoomProducer()
    p.name = name
    p.priority = priority
    p.enabled = True

    def _produce(
        *,
        fn: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        ctx: Any,
        span: Any,
        phase: str,
    ) -> dict[str, Any]:
        del fn, args, kwargs, ctx, span, phase
        raise RuntimeError(f"{name} boom")

    p.produce = _produce  # type: ignore[method-assign]
    return p


def _constant_producer(name: str, priority: int, fields: dict[str, Any]) -> FieldProducer:
    """Return a producer that returns ``fields`` on every ``produce`` call."""

    class _ConstantProducer:
        pass

    p = _ConstantProducer()
    p.name = name
    p.priority = priority
    p.enabled = True

    def _produce(
        *,
        fn: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        ctx: Any,
        span: Any,
        phase: str,
    ) -> dict[str, Any]:
        del fn, args, kwargs, ctx, span, phase
        return dict(fields)

    p.produce = _produce  # type: ignore[method-assign]
    return p


def _source_attacher_producer() -> FieldProducer:
    """Return a stub SourceAttacher that injects ``source_location``.

    Task 9.2 introduces I17 enforcement: every ``*.start`` event MUST
    carry ``source_location`` (ADR-0165.1 §96). Tests focused on other
    behaviour (merge order, anomaly wiring, producer isolation) use
    this stub so they can keep emitting ``brain.perceive.start``
    without satisfying the real SourceAttacher machinery. The dedicated
    I17 tests in ``tests/observability/spine/test_i17_enforcement.py``
    pin the enforcement itself.
    """
    return _constant_producer(
        "spine.reflector.source",
        8,
        {
            "source_location": {
                "file": "stub",
                "line": 0,
                "function": "stub",
            }
        },
    )


class _CountingAnomaly:
    """Counts ``on_event`` invocations and records the events seen."""

    def __init__(self) -> None:
        self.calls: list[EventRecord] = []

    def on_event(self, event: EventRecord) -> None:
        self.calls.append(event)


# ── merge order ──────────────────────────────────────────────────────


def test_three_producers_merge_in_priority_order_without_overlap() -> None:
    """Producers merge by ascending priority with disjoint keys preserved."""
    from lca.plugins.observability.spine.emit_pipeline import EmitPipeline

    p_low = _constant_producer("low", 10, {"a": 1, "shared_low": "low-wins"})
    p_mid = _constant_producer("mid", 20, {"b": 2, "shared_mid": "mid"})
    p_high = _constant_producer("high", 30, {"c": 3, "shared_high": "high-loses"})
    p_src = _source_attacher_producer()

    anomaly = _CountingAnomaly()
    pipeline = EmitPipeline(producers=[p_low, p_mid, p_high, p_src], anomaly=anomaly)
    spine = _make_spine()

    record = pipeline.emit(
        execution_point="brain.perceive.start",
        channel="fact",
        span_ctx=_make_span(),
        caller_payload={"caller": 42},
        spine=spine,
    )

    assert isinstance(record, EventRecord)
    # Disjoint keys from each producer land in the final payload.
    assert record.payload["a"] == 1
    assert record.payload["b"] == 2
    assert record.payload["c"] == 3
    # Caller payload is merged on top of the producer fields.
    assert record.payload["caller"] == 42
    # Lower priority (10) ran first → its shared_* key survives.
    assert record.payload["shared_low"] == "low-wins"
    assert record.payload["shared_mid"] == "mid"
    assert record.payload["shared_high"] == "high-loses"


def test_producers_are_sorted_by_priority_each_emit() -> None:
    """Producers supplied out-of-order are sorted before each emit."""
    from lca.plugins.observability.spine.emit_pipeline import EmitPipeline

    p_low = _constant_producer("low", 10, {"order_low": "ten"})
    p_high = _constant_producer("high", 30, {"order_high": "thirty"})
    p_src = _source_attacher_producer()

    anomaly = _CountingAnomaly()
    # Supply high-first; pipeline must sort ascending before merging.
    pipeline = EmitPipeline(producers=[p_high, p_low, p_src], anomaly=anomaly)
    spine = _make_spine()

    record = pipeline.emit(
        execution_point="brain.perceive.start",
        channel="fact",
        span_ctx=_make_span(),
        caller_payload={},
        spine=spine,
    )

    assert record.payload["order_low"] == "ten"
    assert record.payload["order_high"] == "thirty"


def test_disabled_producers_are_skipped() -> None:
    """A producer with ``enabled=False`` MUST NOT contribute fields."""
    from lca.plugins.observability.spine.emit_pipeline import EmitPipeline

    p_off = _constant_producer("off", 10, {"ghost": "should-not-appear"})
    p_off.enabled = False
    p_on = _constant_producer("on", 20, {"live": "kept"})
    p_src = _source_attacher_producer()

    pipeline = EmitPipeline(producers=[p_off, p_on, p_src], anomaly=_CountingAnomaly())
    spine = _make_spine()

    record = pipeline.emit(
        execution_point="brain.perceive.start",
        channel="fact",
        span_ctx=_make_span(),
        caller_payload={},
        spine=spine,
    )

    assert "ghost" not in record.payload
    assert record.payload["live"] == "kept"


# ── anomaly detector wiring ──────────────────────────────────────────


def test_anomaly_detector_is_called_once_per_emit() -> None:
    """``anomaly.on_event`` MUST be called exactly once for each emit."""
    from lca.plugins.observability.spine.emit_pipeline import EmitPipeline

    p = _constant_producer("only", 10, {"k": "v"})
    p_src = _source_attacher_producer()
    anomaly = _CountingAnomaly()
    pipeline = EmitPipeline(producers=[p, p_src], anomaly=anomaly)
    spine = _make_spine()

    pipeline.emit(
        execution_point="brain.perceive.start",
        channel="fact",
        span_ctx=_make_span(),
        caller_payload={},
        spine=spine,
    )
    pipeline.emit(
        execution_point="brain.perceive.start",
        channel="fact",
        span_ctx=_make_span(),
        caller_payload={},
        spine=spine,
    )

    assert len(anomaly.calls) == 2
    # Detector sees the *sealed* EventRecord — payload already merged.
    assert anomaly.calls[0].payload["k"] == "v"
    assert anomaly.calls[0].execution_point == "brain.perceive.start"


def test_anomaly_detector_exception_is_contained() -> None:
    """If the anomaly detector raises, the emit MUST still return a record."""
    from lca.plugins.observability.spine.emit_pipeline import EmitPipeline

    class _BoomAnomaly:
        def on_event(self, event: EventRecord) -> None:
            del event
            raise RuntimeError("anomaly boom")

    p = _constant_producer("only", 10, {"k": "v"})
    p_src = _source_attacher_producer()
    pipeline = EmitPipeline(producers=[p, p_src], anomaly=_BoomAnomaly())
    spine = _make_spine()

    record = pipeline.emit(
        execution_point="brain.perceive.start",
        channel="fact",
        span_ctx=_make_span(),
        caller_payload={"caller": "x"},
        spine=spine,
    )

    assert isinstance(record, EventRecord)
    assert record.payload["k"] == "v"
    assert record.payload["caller"] == "x"


# ── producer-exception isolation ─────────────────────────────────────


def test_producer_exception_does_not_stop_other_producers() -> None:
    """A raising producer MUST NOT prevent subsequent producers from running."""
    from lca.plugins.observability.spine.emit_pipeline import EmitPipeline

    boom = _failing_producer("boom", 10)
    survivor = _constant_producer("survivor", 20, {"survived": True})
    late = _constant_producer("late", 30, {"late_field": 1})
    p_src = _source_attacher_producer()

    anomaly = _CountingAnomaly()
    pipeline = EmitPipeline(producers=[boom, survivor, late, p_src], anomaly=anomaly)
    spine = _make_spine()

    record = pipeline.emit(
        execution_point="brain.perceive.start",
        channel="fact",
        span_ctx=_make_span(),
        caller_payload={},
        spine=spine,
    )

    # The raising producer contributes nothing; survivors still merge.
    assert "boom" not in record.payload
    assert record.payload["survived"] is True
    assert record.payload["late_field"] == 1
    # The pipeline still appends the record and notifies the detector.
    assert len(anomaly.calls) == 1


# ── I12 close-set enforcement ────────────────────────────────────────


def test_unknown_execution_point_is_rejected_at_emit() -> None:
    """An unknown ``execution_point`` MUST surface a ``ValueError`` (I12)."""
    from lca.plugins.observability.spine.emit_pipeline import EmitPipeline

    p = _constant_producer("only", 10, {})
    pipeline = EmitPipeline(producers=[p], anomaly=_CountingAnomaly())
    spine = _make_spine()

    import pytest

    # Sanity guard: every whitelisted EP must be present in EXECUTION_POINTS.
    assert "brain.perceive.start" in EXECUTION_POINTS
    assert "spine.not_a_real_point" not in EXECUTION_POINTS

    with pytest.raises(ValueError, match=r"spine\.not_a_real_point"):
        pipeline.emit(
            execution_point="spine.not_a_real_point",
            channel="fact",
            span_ctx=_make_span(),
            caller_payload={},
            spine=spine,
        )


# ── plugin manifest shape ────────────────────────────────────────────


def test_plugin_manifest_declares_expected_metadata() -> None:
    """The wrapped plugin exposes the canonical id / layer / kind / provides."""
    from lca.harness.plugin_declaration import definition_from_plugin
    from lca.plugins.observability.spine import emit_pipeline

    # Touching the module forces the @plugin decorator to attach
    # ``_lca_definition`` onto the carrier.
    assert hasattr(emit_pipeline, "setup")

    definition = definition_from_plugin(emit_pipeline.setup, module=__name__)
    assert definition.id == "spine.emit_pipeline"
    assert definition.spec.layer == "L1"
    assert definition.provided_capability_keys == ("emit_pipeline",)
    # Layer-1 integration plugin must require the producer surface.
    assert any(req.key.startswith("field_producer") for req in definition.spec.requires)


def test_module_export_surface() -> None:
    """The module exposes ``EmitPipeline`` and ``setup`` in its public surface."""
    import lca.plugins.observability.spine.emit_pipeline as emit_pipeline_module

    assert hasattr(emit_pipeline_module, "EmitPipeline")
    assert hasattr(emit_pipeline_module, "setup")
    assert hasattr(emit_pipeline_module, "I17Violation")
    assert "EmitPipeline" in emit_pipeline_module.__all__
    assert "setup" in emit_pipeline_module.__all__
    assert "I17Violation" in emit_pipeline_module.__all__


# ── EventSink protocol conformance for the capture sink ──────────────


def test_capture_sink_satisfies_event_sink_protocol() -> None:
    """The local capture sink MUST structurally implement ``EventSink``."""
    sink = _CaptureSink()
    assert isinstance(sink, EventSink)
