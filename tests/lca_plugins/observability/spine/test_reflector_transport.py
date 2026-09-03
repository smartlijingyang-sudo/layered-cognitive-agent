"""Unit tests for carrier transport / kernel.run spine emit helpers."""

# ADR-0181 PR-4：旧 EventSpine transport_emit 已退役，transport / kernel.run
# 全部 6 emit 迁到 lca.plugins.events.publishers.spine_reflector_transport。
# EventMechanism 路径下等价覆盖在
# tests/plugins/events/publishers/test_spine_reflector_transport.py。
# 删-when：PR-9 旧 spine 全退役（rg
# lca.infrastructure.observability.spine.transport_emit lca/ = 0 触发）。
from __future__ import annotations

import pytest


pytestmark = pytest.mark.xfail(
    reason=(
        "ADR-0181 PR-4：旧 EventSpine transport_emit 路径已退役。emit_transport_route_* 等价 "
        "EventMechanism 路径覆盖在 tests/plugins/events/publishers/test_spine_reflector_transport.py；"
        "本测试在 PR-9 旧 spine 全退役时删（rg "
        "lca.infrastructure.observability.spine.transport_emit lca/ = 0 触发）。"
    ),
    strict=True,
)


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
        try:
            raise TypeError(
                "MemoryView.__init__() missing 1 required positional argument: 'buffer'"
            )
        except TypeError as exc:
            record = exc_to_record(
                exc,
                boundary="lifecycle.execute",
                run_id="run_transport_test",
                trace_id="trace_x",
            )
        assert emit_exception_caught(record)
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
