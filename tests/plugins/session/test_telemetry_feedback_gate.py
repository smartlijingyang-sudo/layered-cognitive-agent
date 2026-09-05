"""Wave 3: FEEDBACK_ONLY 门控（验收 #10）。"""

from __future__ import annotations

from lca.contracts.protocols.session.telemetry import SharingPolicy, TelemetryRecord
from lca.plugins.session.runtime.store import SessionStore
from lca.plugins.session.telemetry_capture.telemetry_capture import SessionTelemetryCapture


class _CollectBackend:
    def __init__(self) -> None:
        self.records: list[TelemetryRecord] = []

    @property
    def sharing(self) -> SharingPolicy:
        return SharingPolicy.FEEDBACK_ONLY

    def emit(self, record: TelemetryRecord) -> None:
        self.records.append(record)

    def flush(self) -> None:
        return None

    def shutdown(self) -> None:
        return None


def test_feedback_only_without_feedback_emits_nothing() -> None:
    backend = _CollectBackend()
    capture = SessionTelemetryCapture(backend=backend, capture_mode="live")
    store = SessionStore()
    session = store.create("fb1")
    capture.observe_session(session)
    session.append("turn.started.v1", {"turn": 1})
    session.append("message.accepted.v1", {"message_id": "m1", "role": "user", "content_ref": "hi"})
    assert backend.records == []


def test_feedback_only_releases_prefix_on_feedback_record() -> None:
    backend = _CollectBackend()
    capture = SessionTelemetryCapture(backend=backend, capture_mode="live")
    store = SessionStore()
    session = store.create("fb2")
    capture.observe_session(session)
    session.append("turn.started.v1", {"turn": 1})
    session.append("feedback.record.v1", {"text": "good"})
    assert len(backend.records) >= 1
    assert any(r.attributes.get("event.type") == "feedback.record.v1" for r in backend.records)
