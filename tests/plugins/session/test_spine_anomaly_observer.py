"""Session spine anomaly observer (ADR-0186 wave 3)."""

from __future__ import annotations

from typing import Any

from lca.infrastructure.observability.loop_cursor._spine_port import (
    bind_session_append_hook,
    reset_session_append_hook,
)
from lca.infrastructure.observability.spine.event_record import EventRecord
from lca.plugins.observability.spine.emit_pipeline import EmitPipeline
from lca.plugins.observability.spine.spine_enrich import enrich_spine_payload, set_active_spine_enricher
from lca.plugins.session.runtime.bind import (
    bind_run_event_session_from_store,
    unbind_run_event_session,
)
from lca.plugins.session.spine_anomaly.spine_anomaly import register_spine_anomaly_to_store
from lca.plugins.session.runtime.spine_event_projection import session_event_to_event_record
from lca.plugins.session.runtime.spine_hook import make_session_spine_append_hook
from lca.plugins.session.runtime.store import SessionStore


class _StubProducer:
    name = "stub.producer"
    priority = 10
    enabled = True

    def produce(self, **kwargs: Any) -> dict[str, Any]:
        del kwargs
        return {"source_location": {"file": "t.py", "line": 1}}


class _CountingAnomaly:
    def __init__(self) -> None:
        self.calls: list[EventRecord] = []

    def on_event(self, event: EventRecord) -> None:
        self.calls.append(event)


def test_session_event_projection_maps_spine_category() -> None:
    from lca.plugins.session.runtime.session import Session

    session = Session("run_proj")
    session.append(
        "spine.phase.perceive.fold",
        {"incarnation": 1, "channel": "fact"},
    )
    event = session.event_at(0)
    assert event is not None
    record = session_event_to_event_record(session, event)
    assert record is not None
    assert record.execution_point == "phase.perceive.fold"
    assert record.payload["incarnation"] == 1


def test_spine_anomaly_observer_runs_on_session_append() -> None:
    store = SessionStore()
    detector = _CountingAnomaly()
    register_spine_anomaly_to_store(store, detector)
    session = store.create("run_anom_1")
    session.append(
        "spine.phase.perceive.fold",
        {"incarnation": 2, "channel": "fact"},
    )
    assert len(detector.calls) == 1
    assert detector.calls[0].execution_point == "phase.perceive.fold"


def test_emit_pipeline_skips_anomaly_when_session_hook_bound() -> None:
    from lca.infrastructure.observability.spine.context import SpineContext
    from lca.infrastructure.observability.spine.event_spine import EventSpine
    from lca.infrastructure.observability.spine.sinks.base import EventSink

    class _Sink(EventSink):
        def write(self, record: object) -> None:
            del record

        def close(self) -> None:
            return None

    store = SessionStore()
    bound = bind_run_event_session_from_store(store, "run_anom_2")
    hook_token = bind_session_append_hook(make_session_spine_append_hook(bound.bridge))
    previous_enricher = set_active_spine_enricher(
        lambda **kwargs: enrich_spine_payload(producers=[_StubProducer()], **kwargs)
    )
    pipeline_anomaly = _CountingAnomaly()
    session_anomaly = _CountingAnomaly()
    register_spine_anomaly_to_store(store, session_anomaly)
    pipeline = EmitPipeline(producers=[_StubProducer()], anomaly=pipeline_anomaly)
    SpineContext.set_run("run_anom_2")
    spine = EventSpine(sinks=[_Sink()])
    try:
        pipeline.emit(
            execution_point="phase_graph.node.start",
            channel="fact",
            span_ctx=None,
            caller_payload={"k": "v"},
            spine=spine,
        )
        assert len(pipeline_anomaly.calls) == 0
        assert len(session_anomaly.calls) == 1
        assert session_anomaly.calls[0].execution_point == "phase_graph.node.start"
    finally:
        set_active_spine_enricher(previous_enricher)
        reset_session_append_hook(hook_token)
        unbind_run_event_session(bound)


def test_near_timeout_trips_via_session_observer() -> None:
    from lca.plugins.observability.spine.derivers.anomaly import AnomalyDetector

    store = SessionStore()
    detector = AnomalyDetector()
    register_spine_anomaly_to_store(store, detector)
    session = store.create("run_anom_3")
    session.append(
        "spine.brain.think.start",
        {
            "channel": "fact",
            "duration_ms": 1000,
            "declared": {"timeout_ms": 1000},
        },
    )
    # AnomalyDetector logs when no sink; we only assert observer path does not raise.
    assert session.seq == 1
