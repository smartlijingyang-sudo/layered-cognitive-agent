"""Spine enrich at Session append hook (ADR-0186 wave 2)."""

from __future__ import annotations

from typing import Any

import pytest

from lca.infrastructure.observability.loop_cursor._spine_port import (
    bind_session_append_hook,
    reset_session_append_hook,
)
from lca.infrastructure.observability.spine.context import SpineContext
from lca.infrastructure.observability.spine.event_spine import EventSpine
from lca.infrastructure.observability.spine.sinks.base import EventSink
from lca.plugins.observability.spine.spine_enrich import (
    I17Violation,
    enrich_spine_payload,
    set_active_spine_enricher,
)
from lca.plugins.session.runtime.bind import (
    bind_run_event_session_from_store,
    unbind_run_event_session,
)
from lca.plugins.session.runtime.spine_hook import make_session_spine_append_hook
from lca.plugins.session.runtime.store import SessionStore


class _StubProducer:
    name = "stub.producer"
    priority = 10
    enabled = True

    def produce(self, **kwargs: Any) -> dict[str, Any]:
        del kwargs
        return {"source_location": {"file": "t.py", "line": 1}}


class _RecordingSink(EventSink):
    def __init__(self) -> None:
        self.records: list[Any] = []

    def write(self, record: object) -> None:
        self.records.append(record)

    def close(self) -> None:
        return None


def test_session_hook_enriches_before_append() -> None:
    store = SessionStore()
    bound = bind_run_event_session_from_store(store, "run_enrich_1")
    token = bind_session_append_hook(make_session_spine_append_hook(bound.bridge))
    previous = set_active_spine_enricher(
        lambda **kwargs: enrich_spine_payload(producers=[_StubProducer()], **kwargs)
    )
    SpineContext.set_run("run_enrich_1")
    sink = _RecordingSink()
    spine = EventSpine(sinks=[sink])
    try:
        spine.append(
            execution_point="phase_graph.node.start",
            channel="fact",
            caller_payload={"k": "v"},
        )
        session = bound.bridge.inner
        assert session.seq == 1
        event = session.event_at(0)
        assert event is not None
        assert event.data["source_location"]["file"] == "t.py"
        assert event.data["k"] == "v"
        assert not sink.records, "Session hook path must not write EventSpine sinks"
    finally:
        set_active_spine_enricher(previous)
        reset_session_append_hook(token)
        unbind_run_event_session(bound)


def test_session_hook_i17_propagates_without_sink_fallback() -> None:
    store = SessionStore()
    bound = bind_run_event_session_from_store(store, "run_enrich_2")
    token = bind_session_append_hook(make_session_spine_append_hook(bound.bridge))
    previous = set_active_spine_enricher(
        lambda **kwargs: enrich_spine_payload(producers=[], **kwargs)
    )
    SpineContext.set_run("run_enrich_2")
    sink = _RecordingSink()
    spine = EventSpine(sinks=[sink])
    try:
        with pytest.raises(I17Violation):
            spine.append(
                execution_point="phase_graph.node.start",
                channel="fact",
                caller_payload={},
            )
        assert bound.bridge.inner.seq == 0
        assert not sink.records
    finally:
        set_active_spine_enricher(previous)
        reset_session_append_hook(token)
        unbind_run_event_session(bound)
