"""All three wrap kinds feed ``emit_pipeline`` (Task 7.1.2).

ADR-0165.1 §7.6.4 defines three wrap kinds. This module pins that each
one reaches the *same* ``EmitPipeline`` through the *same* accessor seam,
so no kind can drift onto a private emission path:

===================  ==================================================
Wrap kind            Entry point under test
===================  ==================================================
``assembler``        ``wrap_instrument`` (and ``GraphAssembler`` via
                     ``wrap_executor``)
``ctx_intercept``    ``install_ctx_intercept_hook``
``ctx_effect``       ``install_ctx_effect_hook``
===================  ==================================================

Unlike the ``wrap_instrument`` unit tests (which use ``FieldProducer``
doubles), these tests wire the **real** producers —
:class:`SignatureFieldProducer`, :class:`SourceAttacher` and
:class:`SpanTreeFieldProducer` — so the assertions prove the live
plugins' keys (``signature_fingerprint`` / ``source_location`` /
``span_id``) actually land in the sealed ``EventRecord.payload``.

Deviation from the brief
------------------------
The brief named ``tests/integration/test_e2e_full_pipeline.py`` driving a
profile boot. That directory does not exist and the ``spine.core`` boot
wiring is PR-8 work (``spine.emit_pipeline.setup`` still raises
``NotImplementedError``), so a profile-boot e2e cannot run yet. These
focused tests cover the same contract at the seam that PR-8 will install.
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
from lca.plugins.observability.spine.emit_pipeline import EmitPipeline
from lca.plugins.observability.spine.reflectors.signature import SignatureFieldProducer
from lca.plugins.observability.spine.reflectors.source import SourceAttacher
from lca.plugins.observability.spine.runtime_hooks import (
    CTX_INTERCEPT_PROVENANCE,
    install_ctx_effect_hook,
    install_ctx_intercept_hook,
    resolve_active_pipeline,
)
from lca.plugins.observability.spine.spantree import SpanTreeFieldProducer

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


class _NoopAnomaly:
    """Anomaly detector satisfying ``EmitPipeline``'s ``_AnomalyLike``."""

    def on_event(self, event: EventRecord) -> None:
        del event


class _FakeCtx:
    """Minimal ``cordis.Context`` stand-in exposing only ``effect``.

    ``install_ctx_effect_hook`` / ``install_ctx_intercept_hook`` only ever
    touch ``ctx.effect(dispose, label=...)``; a real ``Context`` would
    drag plugin-kernel boot into a unit test for no added coverage.
    """

    def __init__(self) -> None:
        self.disposers: list[tuple[Any, str]] = []

    def effect(self, dispose: Any, *, label: str = "effect") -> None:
        self.disposers.append((dispose, label))

    def dispose_all(self) -> None:
        """Run disposers in reverse registration order, like cordis does."""
        for dispose, _label in reversed(self.disposers):
            dispose()
        self.disposers.clear()


@pytest.fixture
def wired_spine() -> Any:
    """Install a real-producer ``EmitPipeline`` + capture spine, then tear down.

    Yields the ``_CaptureSink`` so each test reads the sealed records.
    The three producers are the live plugin classes, not doubles, so the
    asserted keys are the ones production emits.
    """
    SpineContext.set_run("wrap-kinds-emit-pipeline-test")
    sink = _CaptureSink()
    spine = EventSpine(sinks=[sink])
    pipeline = EmitPipeline(
        producers=[
            SpanTreeFieldProducer(),
            SourceAttacher(),
            SignatureFieldProducer(),
        ],
        anomaly=_NoopAnomaly(),
    )
    set_active_pipeline_accessor(lambda: pipeline)
    set_active_spine_accessor(lambda: spine)
    try:
        yield sink
    finally:
        set_active_pipeline_accessor(None)
        set_active_spine_accessor(None)


def _assert_auto_source_fields(record: EventRecord) -> None:
    """Assert the three real producers each contributed to ``record``.

    - ``signature_fingerprint`` — :class:`SignatureFieldProducer`
    - ``source_location``       — :class:`SourceAttacher` (I17)
    - ``span_id``               — :class:`SpanTreeFieldProducer`
    """
    payload = record.payload
    assert "signature_fingerprint" in payload, (
        f"SignatureFieldProducer did not contribute to {record.execution_point}"
    )
    assert payload["signature_fingerprint"], "signature_fingerprint must be non-empty"
    assert "source_location" in payload, (
        f"SourceAttacher did not contribute to {record.execution_point}"
    )
    assert "span_id" in payload, (
        f"SpanTreeFieldProducer did not contribute to {record.execution_point}"
    )


# ── wrap kind 1: assembler (wrap_instrument) ─────────────────────────


def test_assembler_wrap_kind_feeds_emit_pipeline(wired_spine: _CaptureSink) -> None:
    """``wrap_instrument`` events carry all three real producers' fields."""

    def sample(x: int, y: int = 0) -> int:
        """Add two integers."""
        return x + y

    wrapped = wrap_instrument(sample)
    assert wrapped(2, y=3) == 5

    records = wired_spine.records
    assert len(records) == 2
    start_record, end_record = records
    assert start_record.execution_point == "phase_graph.node.start"
    assert end_record.execution_point == "phase_graph.node.end"
    _assert_auto_source_fields(start_record)
    _assert_auto_source_fields(end_record)
    assert end_record.outcome == "success"


def test_assembler_wrap_kind_async_feeds_emit_pipeline(
    wired_spine: _CaptureSink,
) -> None:
    """The async ``wrap_instrument`` branch uses the same pipeline seam."""

    async def sample() -> str:
        """Return a constant."""
        return "ok"

    wrapped = wrap_instrument(sample)
    assert asyncio.run(wrapped()) == "ok"

    records = wired_spine.records
    assert len(records) == 2
    for record in records:
        _assert_auto_source_fields(record)


# ── wrap kind 2: ctx_intercept ───────────────────────────────────────


def test_ctx_intercept_wrap_kind_feeds_emit_pipeline(
    wired_spine: _CaptureSink,
) -> None:
    """An intercepted host method emits pipeline-fed start/end events."""

    class _Host:
        def run(self, value: int) -> int:
            """Double the input."""
            return value * 2

    host = _Host()
    ctx = _FakeCtx()
    install_ctx_intercept_hook(
        ctx,
        target=host,
        method_name="run",
        execution_point_start="brain.think.start",
        execution_point_end="brain.think.end",
    )

    assert host.run(21) == 42

    records = wired_spine.records
    assert len(records) == 2
    start_record, end_record = records
    assert start_record.execution_point == "brain.think.start"
    assert end_record.execution_point == "brain.think.end"
    _assert_auto_source_fields(start_record)
    _assert_auto_source_fields(end_record)

    # Marker attribution distinguishes this kind from the assembler wrap.
    assert getattr(host.run, "wrap_provenance", None) == CTX_INTERCEPT_PROVENANCE

    # ctx.effect owns the un-patch; disposing restores the original.
    ctx.dispose_all()
    assert getattr(host.run, "wrap_provenance", None) is None


def test_ctx_intercept_wrap_kind_emits_failure_and_reraises(
    wired_spine: _CaptureSink,
) -> None:
    """An exception inside an intercepted method still emits through the pipeline."""

    class _Host:
        def run(self) -> None:
            """Always raises."""
            raise RuntimeError("kaboom")

    host = _Host()
    ctx = _FakeCtx()
    install_ctx_intercept_hook(
        ctx,
        target=host,
        method_name="run",
        execution_point_start="brain.think.start",
        execution_point_end="brain.think.end",
    )

    with pytest.raises(RuntimeError, match="kaboom"):
        host.run()

    records = wired_spine.records
    assert len(records) == 2
    _assert_auto_source_fields(records[0])
    _assert_auto_source_fields(records[1])
    assert records[1].outcome == "failure"
    assert records[1].channel == "error"
    # ADR-2026-09-02-i17-stream-align §B: the failure payload must
    # carry the structured traceback fields so coding-agent tooling
    # can render the failure without re-raising it.
    failure_payload = records[1].payload
    assert failure_payload["exc_type"] == "RuntimeError"
    assert failure_payload["exception_class"] == "RuntimeError"
    assert failure_payload["exception_message"] == "kaboom"
    assert failure_payload["reason"] == "kaboom"
    assert "RuntimeError: kaboom" in failure_payload["traceback_text"]
    assert failure_payload["cause_chain"] == []


def test_ctx_intercept_wrap_kind_is_idempotent(wired_spine: _CaptureSink) -> None:
    """Re-installing over an instrumented attribute must not double-emit."""

    class _Host:
        def run(self) -> int:
            """Return a constant."""
            return 1

    host = _Host()
    ctx = _FakeCtx()
    for _ in range(2):
        install_ctx_intercept_hook(
            ctx,
            target=host,
            method_name="run",
            execution_point_start="brain.think.start",
            execution_point_end="brain.think.end",
        )

    assert host.run() == 1
    # Two events, not four: the marker check refused the second wrap.
    assert len(wired_spine.records) == 2


# ── wrap kind 3: ctx_effect ──────────────────────────────────────────


def test_ctx_effect_wrap_kind_feeds_emit_pipeline(wired_spine: _CaptureSink) -> None:
    """Context lifecycle start/end events carry all three producers' fields."""
    ctx = _FakeCtx()
    install_ctx_effect_hook(
        ctx,
        start_execution_point="kernel.boot.start",
        end_execution_point="kernel.boot.completed",
        payload={"profile": "test-profile"},
    )

    # The start event is emitted eagerly; the end event waits for dispose.
    assert len(wired_spine.records) == 1
    start_record = wired_spine.records[0]
    assert start_record.execution_point == "kernel.boot.start"
    _assert_auto_source_fields(start_record)
    assert start_record.payload["profile"] == "test-profile"

    ctx.dispose_all()

    assert len(wired_spine.records) == 2
    end_record = wired_spine.records[1]
    assert end_record.execution_point == "kernel.boot.completed"
    _assert_auto_source_fields(end_record)
    assert end_record.outcome == "success"


# ── the seam itself ──────────────────────────────────────────────────


def test_all_wrap_kinds_resolve_the_same_pipeline_instance(
    wired_spine: _CaptureSink,
) -> None:
    """One accessor install must serve every wrap kind.

    This is the Task 7.1.2 invariant: ``resolve_active_pipeline`` is the
    single seam, so a future wrap kind cannot silently bypass the
    producer merge by resolving its own pipeline.
    """
    del wired_spine
    pipeline = resolve_active_pipeline()
    assert pipeline is not None
    assert isinstance(pipeline, EmitPipeline)
    # The producer set is the live plugin trio, priority-sorted.
    names = [producer.name for producer in pipeline.producers]
    assert names == [
        "spine.spantree",
        "spine.reflector.source",
        "spine.reflector.signature",
    ]


def test_wrap_kinds_are_silent_without_a_wired_spine() -> None:
    """With no accessors installed, every wrap kind degrades to a no-op.

    Pre-boot and unit-test paths must not raise just because the spine is
    not wired yet — the documented degradation for all three kinds.
    """
    set_active_pipeline_accessor(None)
    set_active_spine_accessor(None)

    class _Host:
        def run(self) -> int:
            """Return a constant."""
            return 7

    host = _Host()
    ctx = _FakeCtx()
    install_ctx_intercept_hook(
        ctx,
        target=host,
        method_name="run",
        execution_point_start="brain.think.start",
        execution_point_end="brain.think.end",
    )
    install_ctx_effect_hook(
        ctx,
        start_execution_point="kernel.boot.start",
        end_execution_point="kernel.boot.completed",
    )

    assert host.run() == 7
    assert wrap_instrument(lambda: 3)() == 3
    ctx.dispose_all()


# ── I17 traceback surfacing (ADR-2026-09-02-i17-traceback §D1) ────────


class _FakeI17ViolationError(Exception):
    """Test double mimicking the real ``I17Violation`` class.

    Verified via duck-type rather than a static import to keep the
    assembler import surface unchanged.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        # Override the qualname so the duck-typed check in
        # ``_is_i17_violation`` accepts this instance.
        self.__class__.__module__ = "lca.plugins.observability.spine.emit_pipeline"
        # The duck-typed check in ``_is_i17_violation`` accepts this
        # instance by matching ``cls.__module__``/``cls.__name__`` after
        # rebinding to the production qualname.
        self.__class__.__name__ = "I17Violation"


def test_i17_rejection_emits_traceback_to_stderr(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """ADR-2026-09-02 §D1: an I17 violation in wrap_instrument MUST
    surface a traceback — the original ``log.warning(..., err=%s)``
    dropped it on the floor and made incidents unrecoverable.

    We wrap the spine accessor so that ``*.start`` emissions trip the
    real ``I17Violation`` path through the public seam, and assert the
    log line carries ``exc_info=True`` (so ``caplog.records[i].exc_info``
    is populated, which is what makes the traceback appear).
    """

    class _RaisingSpine:
        def append(self, *args: Any, **kwargs: Any) -> None:
            raise _FakeI17ViolationError("I17: synthetic for test")

    captured: list[dict[str, Any]] = []

    def _capture(**payload: Any) -> Any:
        captured.append(payload)
        # Re-raise the I17 to drive the real wrapper path.
        raise _FakeI17ViolationError(
            "I17: execution_point='phase_graph.node.start' requires "
            "'source_location' in payload (ADR-0165.1 §96); "
            "SourceAttacher producer missing or disabled"
        )

    class _RaisingPipeline:
        def emit(self, *args: Any, **kwargs: Any) -> None:
            _capture(**kwargs)

    def sample() -> int:
        """Sentinel."""
        return 0

    set_active_spine_accessor(lambda: _RaisingSpine())
    set_active_pipeline_accessor(lambda: _RaisingPipeline())
    try:
        with caplog.at_level("WARNING", logger="lca.harness.declarative.compile.instrument_wrap"):
            wrapped = wrap_instrument(sample)
            wrapped()
    finally:
        set_active_spine_accessor(None)
        set_active_pipeline_accessor(None)

    # The I17 path must use log.error so it stands out from generic
    # sink failures, and must carry exc_info so the traceback is on
    # the log record.
    error_records = [
        r for r in caplog.records if r.levelname == "ERROR" and "I17 rejected" in r.getMessage()
    ]
    assert error_records, (
        "wrap_instrument silently swallowed the I17 violation; "
        "no 'I17 rejected' ERROR record was emitted. This is the "
        "exact regression ADR-2026-09-02 §D1 was written to prevent."
    )
    assert error_records[0].exc_info, (
        "I17 rejection log line has exc_info=None — traceback was dropped on the floor."
    )
