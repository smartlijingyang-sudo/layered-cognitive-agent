"""``wrap_instrument`` MUST drive ``EmitPipeline.emit`` (PR-7.1.1).

When the spine's emit pipeline is wired, ``wrap_instrument(fn)``
funnels every emitted event through ``EmitPipeline.emit(...)`` so
that every enabled ``FieldProducer`` (signature / context / runtime /
source) contributes its keys into ``EventRecord.payload``. When the
pipeline is NOT wired (unit tests, pre-boot paths), ``wrap_instrument``
falls back to the legacy ``EventSpine.append(...)`` call so the
assembler contract continues to hold.

These tests pin the contract from the outside without depending on
the real reflector plugins - small in-test ``FieldProducer`` doubles
stand in for the signature / context / runtime / source axes so the
test stays self-contained and exercises the merge path.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from lca.harness.declarative.compile.instrument_wrap import (
    set_active_pipeline_accessor,
    set_active_spine_accessor,
    wrap_instrument,
)
from lca.infrastructure.observability.spine.context import SpineContext
from lca.infrastructure.observability.spine.event_record import EventRecord
from lca.infrastructure.observability.spine.event_spine import EventSpine

# -- helpers -----------------------------------------------------------


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
    """Return a fresh ``EventSpine`` with capture sink (autouse passthrough hook)."""
    SpineContext.set_run("wrap-emit-pipeline-test")
    sink = _CaptureSink()
    return EventSpine(sinks=[sink])


def _make_field_producer(
    name: str,
    priority: int,
    fields: dict[str, Any],
) -> Any:
    """Return a small ``FieldProducer`` double that returns ``fields`` per call."""

    class _Producer:
        name: str
        priority: int
        enabled: bool

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
            return dict(fields)

    p = _Producer()
    p.name = name
    p.priority = priority
    p.enabled = True
    return p


def _noop_anomaly() -> Any:
    """Return a no-op anomaly detector satisfying the EmitPipeline protocol."""

    class _Anomaly:
        def on_event(self, event: EventRecord) -> None:
            del event

    return _Anomaly()


def _install_pipeline_accessor(spine: EventSpine, producers: list[Any] | None = None) -> Any:
    """Build + install a process-local ``EmitPipeline`` accessor.

    Returns the ``EmitPipeline`` so tests can inspect its producer set
    or call methods directly. The previous accessor (if any) is
    restored by the caller via the explicit ``finally`` block.
    """
    from lca.plugins.observability.spine.emit_pipeline import EmitPipeline

    pipeline = EmitPipeline(producers=list(producers or []), anomaly=_noop_anomaly())
    set_active_pipeline_accessor(lambda: pipeline)
    set_active_spine_accessor(lambda: spine)
    return pipeline


async def _await(awaitable: Any) -> Any:
    """Await any awaitable in a synchronous test context.

    Helper used by tests that need to drive an awaitable returned by
    a wrapped async callable without depending on pytest-asyncio.
    """
    return await awaitable


# -- tests: pipeline wired -> producers contribute --------------------


def test_wrap_instrument_signature_producer_contributes_keys_to_event() -> None:
    """When an emit pipeline is wired, ``wrap_instrument`` MUST call ``EmitPipeline.emit``.

    A signature-axis ``FieldProducer`` double injecting
    ``signature_fingerprint`` / ``input_params`` / ``output_schema`` /
    ``docstring_captured`` MUST see every key land in the sealed
    ``EventRecord.payload`` for the ``.start`` and ``.end`` events.
    """
    spine = _make_spine()
    signature_producer = _make_field_producer(
        "spine.reflector.signature.stub",
        priority=100,
        fields={
            "signature_fingerprint": "abc123",
            "input_params": "((), {})",
            "output_schema": {},
            "docstring_captured": "do thing",
        },
    )
    # I17 requires every ``*.start`` event to carry ``source_location``;
    # add a source-axis stub producer so the I17 check does not fire.
    source_producer = _make_field_producer(
        "spine.reflector.source.stub",
        priority=8,
        fields={
            "source_location": {
                "file": "stub.py",
                "line": 1,
                "function": "stub",
            },
        },
    )
    _install_pipeline_accessor(spine, producers=[source_producer, signature_producer])
    try:

        def sample(x: int, y: int = 0) -> int:
            """Add two integers."""
            return x + y

        wrapped = wrap_instrument(sample)
        result = wrapped(2, y=3)

        assert result == 5
        records = spine._sinks[0].records  # type: ignore[attr-defined]
        assert len(records) == 2
        start_record, end_record = records

        # Signature keys present on the start event.
        assert start_record.payload["signature_fingerprint"] == "abc123"
        assert start_record.payload["input_params"] == "((), {})"
        assert "output_schema" in start_record.payload
        assert start_record.payload["docstring_captured"] == "do thing"
        # I17 source_location also present.
        assert start_record.payload["source_location"] == {
            "file": "stub.py",
            "line": 1,
            "function": "stub",
        }

        # Signature keys still present on the end event (producer is phase-agnostic).
        assert end_record.payload["signature_fingerprint"] == "abc123"
        # End event does not require source_location (I17 only checks *.start).
    finally:
        set_active_pipeline_accessor(None)
        set_active_spine_accessor(None)


def test_wrap_instrument_context_runtime_source_producers_all_contribute() -> None:
    """signature / context / runtime / source producers all merge into payload.

    Each axis contributes a distinct key; all four keys land in the
    final ``EventRecord.payload`` so the D11 auto-source contract holds
    end-to-end through ``wrap_instrument``.
    """
    spine = _make_spine()
    source_producer = _make_field_producer(
        "spine.reflector.source.stub",
        priority=8,
        fields={"source_location": {"file": "s.py", "line": 1, "function": "f"}},
    )
    context_producer = _make_field_producer(
        "spine.reflector.context.stub",
        priority=20,
        fields={
            "preconditions": "captured_at_phase=pre",
            "budget_at_entry": {"tokens": 100},
        },
    )
    runtime_producer = _make_field_producer(
        "spine.reflector.runtime.stub",
        priority=30,
        fields={
            "duration_ms": 12.5,
            "return_value_fingerprint": "deadbeef",
        },
    )
    signature_producer = _make_field_producer(
        "spine.reflector.signature.stub",
        priority=100,
        fields={"signature_fingerprint": "cafef00d"},
    )
    _install_pipeline_accessor(
        spine,
        producers=[
            source_producer,
            context_producer,
            runtime_producer,
            signature_producer,
        ],
    )
    try:

        async def async_sample() -> str:
            """Return a constant for the post event."""
            return "ok"

        wrapped = wrap_instrument(async_sample)
        # wrapped returns an awaitable; drive it via asyncio.run.
        result: Any = asyncio.run(_await(wrapped()))

        assert result == "ok"
        records = spine._sinks[0].records  # type: ignore[attr-defined]
        assert len(records) == 2
        start_record, end_record = records

        # Every axis contributed a key.
        assert "source_location" in start_record.payload
        assert "preconditions" in start_record.payload
        assert "duration_ms" in end_record.payload
        assert "signature_fingerprint" in end_record.payload
    finally:
        set_active_pipeline_accessor(None)
        set_active_spine_accessor(None)


# -- tests: no pipeline -> legacy fallback still works ----------------


def test_wrap_instrument_falls_back_to_direct_spine_append_without_pipeline() -> None:
    """When no pipeline is installed, ``wrap_instrument`` MUST fall back to direct ``spine.append``.

    The assembler contract from PR-4 still holds: the legacy
    ``EventSpine.append(...)`` path is the source of truth when the
    emit pipeline is not yet wired (early unit tests, pre-boot).
    """
    spine = _make_spine()
    # Only the spine accessor is installed; no pipeline accessor.
    set_active_spine_accessor(lambda: spine)
    set_active_pipeline_accessor(None)
    try:

        def sample() -> int:
            """Legacy-path sample."""
            return 42

        wrapped = wrap_instrument(sample)
        result = wrapped()

        assert result == 42
        records = spine._sinks[0].records  # type: ignore[attr-defined]
        assert len(records) == 2
        start_record, end_record = records

        # Legacy payload keys (args_count / kwargs_count /
        # return_value_fingerprint) remain - no producer keys injected.
        assert "args_count" in start_record.payload
        assert "return_value_fingerprint" in end_record.payload
        # No FieldProducer keys because no pipeline was installed.
        assert "signature_fingerprint" not in start_record.payload
        assert "source_location" not in start_record.payload
    finally:
        set_active_spine_accessor(None)
        set_active_pipeline_accessor(None)


def test_wrap_instrument_handles_exception_via_emit_pipeline() -> None:
    """An exception inside the wrapped callable MUST route through the pipeline.

    The ``.end`` event uses ``outcome="failure"`` and the pipeline
    still emits; the exception propagates to the caller after the
    record is sealed.
    """
    spine = _make_spine()
    source_producer = _make_field_producer(
        "spine.reflector.source.stub",
        priority=8,
        fields={"source_location": {"file": "s.py", "line": 1, "function": "f"}},
    )
    signature_producer = _make_field_producer(
        "spine.reflector.signature.stub",
        priority=100,
        fields={"signature_fingerprint": "boom"},
    )
    _install_pipeline_accessor(spine, producers=[source_producer, signature_producer])
    try:

        def sample() -> None:
            """Always raises."""
            raise RuntimeError("kaboom")

        wrapped = wrap_instrument(sample)
        with pytest.raises(RuntimeError, match="kaboom"):
            wrapped()

        # Two events: .start + .end(failure). Producer keys land in both.
        records = spine._sinks[0].records  # type: ignore[attr-defined]
        assert len(records) == 2
        start_record, end_record = records
        assert start_record.payload["signature_fingerprint"] == "boom"
        assert end_record.payload["signature_fingerprint"] == "boom"
        assert end_record.outcome == "failure"
    finally:
        set_active_pipeline_accessor(None)
        set_active_spine_accessor(None)


# -- tests: marker attributes are preserved across the refactor -------


def test_wrap_instrument_preserves_instrumented_markers_with_pipeline() -> None:
    """The PR-4 Layer-3 markers MUST be intact regardless of which emit path runs.

    ``__lca_instrumented__`` and ``wrap_provenance`` are the
    ``assert_all_instrumented`` invariants; the refactor MUST NOT
    weaken them.
    """
    spine = _make_spine()
    _install_pipeline_accessor(spine, producers=[])
    try:

        def sample() -> None:
            """Marker-preservation probe."""
            return None

        wrapped = wrap_instrument(sample)
        assert getattr(wrapped, "__lca_instrumented__", False) is True
        assert getattr(wrapped, "wrap_provenance", None) == "assembler"
        assert getattr(wrapped, "__wrapped__", None) is sample
    finally:
        set_active_pipeline_accessor(None)
        set_active_spine_accessor(None)


def test_wrap_instrument_bypasses_emit_pipeline_when_session_ssot_hook() -> None:
    """Production Session hook: enrich at hook; wrap must not call EmitPipeline.emit."""
    from lca.infrastructure.observability.loop_cursor._spine_port import (
        bind_session_append_hook,
        reset_session_append_hook,
    )
    from lca.plugins.observability.spine.spine_enrich import (
        enrich_spine_payload,
        set_active_spine_enricher,
    )
    from lca.plugins.session.runtime.bind import (
        bind_run_event_session_from_store,
        unbind_run_event_session,
    )
    from lca.plugins.session.runtime.spine_hook import make_session_spine_append_hook
    from lca.plugins.session.runtime.store import SessionStore

    store = SessionStore()
    bound = bind_run_event_session_from_store(store, "wrap_ssot_bypass")
    signature_producer = _make_field_producer(
        "spine.reflector.signature.stub",
        priority=100,
        fields={"signature_fingerprint": "pipeline_only"},
    )
    source_producer = _make_field_producer(
        "spine.reflector.source.stub",
        priority=8,
        fields={"source_location": {"file": "s.py", "line": 1, "function": "f"}},
    )
    SpineContext.set_run("wrap_ssot_bypass")
    sink = _CaptureSink()
    spine = EventSpine(sinks=[sink])
    hook_token = bind_session_append_hook(make_session_spine_append_hook(bound.bridge))
    pipeline_emit_count = 0
    real_pipeline = _install_pipeline_accessor(
        spine, producers=[source_producer, signature_producer]
    )
    original_emit = real_pipeline.emit

    def _counting_emit(**kwargs: Any) -> EventRecord:
        nonlocal pipeline_emit_count
        pipeline_emit_count += 1
        return original_emit(**kwargs)

    real_pipeline.emit = _counting_emit  # type: ignore[method-assign]
    previous_enricher = set_active_spine_enricher(
        lambda **kwargs: enrich_spine_payload(
            producers=[source_producer, signature_producer], **kwargs
        )
    )
    try:

        def sample() -> int:
            """SSOT bypass probe."""
            return 7

        wrapped = wrap_instrument(sample)
        assert wrapped() == 7
        assert pipeline_emit_count == 0
        session = bound.bridge.inner
        assert session.seq == 2
        start_event = session.event_at(0)
        assert start_event is not None
        assert start_event.data["signature_fingerprint"] == "pipeline_only"
        assert not sink.records, "SSOT hook path must not write EventSpine sinks"
    finally:
        set_active_spine_enricher(previous_enricher)
        reset_session_append_hook(hook_token)
        unbind_run_event_session(bound)
        set_active_pipeline_accessor(None)
        set_active_spine_accessor(None)
