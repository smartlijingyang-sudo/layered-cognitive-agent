"""Unit tests for carrier transport / kernel.run spine emit helpers."""

from __future__ import annotations

from lca.harness.declarative.compile.instrument_wrap import set_active_spine_accessor
from lca.infrastructure.observability.spine import transport_emit
from lca.infrastructure.observability.spine.event_record import EventRecord
from lca.infrastructure.observability.spine.event_spine import EventSpine
from lca.infrastructure.observability.spine.sinks.base import EventSink


class _CaptureSink:
    def __init__(self) -> None:
        self.records: list[EventRecord] = []

    def write(self, record: EventRecord) -> None:
        self.records.append(record)

    def close(self) -> None:
        return None


def test_emit_helpers_noop_without_active_spine() -> None:
    previous = set_active_spine_accessor(None)
    try:
        assert transport_emit.emit_transport_route_enter(path="/runs", method="POST") is None
        assert transport_emit.emit_kernel_run_start(run_id="run_x") is None
    finally:
        set_active_spine_accessor(previous)


def test_emit_transport_and_kernel_run_chain() -> None:
    sink = _CaptureSink()
    spine = EventSpine(sinks=[sink], run_id="run_transport_test")
    previous = set_active_spine_accessor(lambda: spine)
    try:
        assert transport_emit.emit_transport_route_enter(
            path="/runs", method="POST", run_id="run_transport_test"
        )
        assert transport_emit.emit_kernel_run_start(run_id="run_transport_test", trace_id="trace_x")
        assert transport_emit.emit_carrier_exception_caught(
            boundary="lifecycle.execute",
            exc_type="TypeError",
            message="MemoryView.__init__() missing 1 required positional argument: 'buffer'",
            run_id="run_transport_test",
        )
        assert transport_emit.emit_kernel_run_stop(run_id="run_transport_test", outcome="failure")
        assert transport_emit.emit_transport_route_exit(
            path="/runs", method="POST", outcome="failure", run_id="run_transport_test"
        )
    finally:
        set_active_spine_accessor(previous)
        spine.close()

    points = [r.execution_point for r in sink.records]
    assert points == [
        "transport.route.enter",
        "kernel.run.start",
        "exception.caught",
        "kernel.run.stop",
        "transport.route.exit",
    ]
    assert isinstance(sink, EventSink)
