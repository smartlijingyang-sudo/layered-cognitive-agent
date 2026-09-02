"""``SpineCore.append`` must satisfy ``SpineLike`` (PR-fix).

Lock the contract that lets
``lca.plugins.observability.writable_matrix.assembly.setup`` bind the
holder directly. Pre-fix, this failed at first emit with
``AttributeError: 'SpineCore' object has no attribute 'append'`` and
broke every perceive.run before any LLM / think / tool event could
land in ``events.jsonl``.

The test pins three properties:

* ``SpineLike`` is ``@runtime_checkable`` — failed binds raise
  :class:`TypeError` at boot, not at first emit.
* ``SpineCore`` is itself a ``SpineLike``.
* :class:`SpineEmitter.bind` rejects objects without ``.append``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from lca.infrastructure.observability.spine.event_record import EventRecord
from lca.infrastructure.observability.spine.event_spine import EventSpine
from lca.infrastructure.observability.writable_matrix.defaults import (
    SpineEmitter,
    SpineLike,
)
from lca.plugins.observability.spine.core import SpineCore


@dataclass
class _CapturingSink:
    """Minimal :class:`EventSink` for round-trip testing."""

    records: list[EventRecord] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.records is None:
            self.records = []

    def write(self, record: EventRecord) -> None:
        self.records.append(record)

    def close(self) -> None:
        return None


def _make_event_spine() -> tuple[EventSpine, _CapturingSink]:
    sink = _CapturingSink()
    return EventSpine(sinks=[sink]), sink


def _make_record(seq: int = 1) -> EventRecord:
    now = datetime.now(timezone.utc)
    return EventRecord(
        execution_point="phase.perceive.fold",
        channel="fact",
        span_id=f"t-{seq}",
        parent_span_id=None,
        sequence=seq,
        epoch=seq,
        causality_id=f"caus-{seq}",
        outcome=None,
        when=now,
        when_corrected=now,
        prev_event_hash=None,
        run_id="r",
        step_id=None,
        payload={"marker": True},
        phase="live",
    )


def test_spine_like_is_runtime_checkable() -> None:
    """``SpineLike`` must be runtime-checkable so bind() can reject bad inputs."""
    assert isinstance(SpineLike, type)
    # runtime_checkable Protocols set _is_runtime_protocol
    assert getattr(SpineLike, "_is_runtime_protocol", False)


def test_spine_core_satisfies_spine_like() -> None:
    es, sink = _make_event_spine()
    core = SpineCore(event_spine=es, file_sink=sink, emit_pipeline=None)
    assert isinstance(core, SpineLike)


def test_spine_core_append_delegates_to_event_spine() -> None:
    es, sink = _make_event_spine()
    core = SpineCore(event_spine=es, file_sink=sink, emit_pipeline=None)
    rec = _make_record()
    # If the shim is wired correctly, the inner sink captures the record.
    core.append(
        execution_point=rec.execution_point,
        channel=rec.channel,
        caller_payload=rec.payload,
        outcome=rec.outcome,
        phase=rec.phase,
        reason=rec.reason,
        when=rec.when,
    )
    assert len(sink.records) == 1
    assert sink.records[0].execution_point == "phase.perceive.fold"


def test_emitter_bind_accepts_spine_core() -> None:
    """Regression: assembly used to bind SpineCore and crash on first emit."""
    es, sink = _make_event_spine()
    core = SpineCore(event_spine=es, file_sink=sink, emit_pipeline=None)
    emitter = SpineEmitter()
    emitter.bind(core)  # must not raise
    emitter.emit(_make_record())
    assert len(sink.records) == 1


def test_emitter_bind_rejects_non_spine_like() -> None:
    """An object without ``.append`` must be rejected at bind(), not at first emit()."""

    class _NotASpine:
        pass

    emitter = SpineEmitter()
    try:
        emitter.bind(_NotASpine())
    except TypeError as exc:
        assert "SpineLike" in str(exc)
        assert "_NotASpine" in str(exc)
    else:
        raise AssertionError("expected TypeError for non-SpineLike bind()")


def test_emitter_bind_accepts_any_object_with_append() -> None:
    """``@runtime_checkable`` only checks method existence, not signature.

    This pins the documented behavior so a future change to `` spines_emit``
    signature is caught here, not at first emit in production.
    """

    class _AnythingWithAppend:
        def append(self, **kwargs: Any) -> None:
            return None

    emitter = SpineEmitter()
    emitter.bind(_AnythingWithAppend())  # must not raise
