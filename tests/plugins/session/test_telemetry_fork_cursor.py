"""Wave 4.2: fork 后 telemetry 游标从 seed 边界开始,不重复外送前缀。"""

from __future__ import annotations

from lca.contracts.protocols.session.telemetry import SharingPolicy, TelemetryRecord
from lca.plugins.session.runtime.fork import fork_session
from lca.plugins.session.runtime.session import Session
from lca.plugins.session.runtime.store import SessionStore
from lca.plugins.session.telemetry_capture.telemetry_capture import (
    SessionTelemetryCapture,
    _seed_telemetry_cursor,
)
from lca_kernel.events.fold import SURFACE_USER_TYPE


class _CollectBackend:
    def __init__(self) -> None:
        self.records: list[TelemetryRecord] = []
        self.sharing = SharingPolicy.FULL

    def emit(self, record: TelemetryRecord) -> None:
        self.records.append(record)

    def flush(self) -> None:
        return None

    def shutdown(self) -> None:
        return None


def test_forked_child_telemetry_cursor_skips_seed_prefix() -> None:
    backend = _CollectBackend()
    capture = SessionTelemetryCapture(backend=backend, capture_mode="on_demand")
    store = SessionStore()

    parent = store.create("parent")
    parent.append("turn.started.v1", {"turn": 1})
    parent.append(SURFACE_USER_TYPE, {"content": "seed"}, surface_op="append")
    parent.append("turn.ended.v1", {"turn": 1, "reason": "done"})

    child = fork_session(store, parent, boundary=2, child_session_id="child")
    capture.reset_handoff_cursor(child.id, through_seq=child.seq - 1)
    assert capture.capture_session(child) == 0

    child.append("turn.started.v1", {"turn": 2})
    delivered = capture.capture_session(child)
    assert delivered >= 1
    assert all(record.attributes.get("event.seq", -1) > 2 for record in backend.records)


def test_seeded_session_attach_resets_cursor_via_helper() -> None:
    backend = _CollectBackend()
    capture = SessionTelemetryCapture(backend=backend, capture_mode="on_demand")
    session = Session("seeded")
    session.append("turn.started.v1", {"turn": 1})
    object.__setattr__(session._header, "is_seeded", True)
    object.__setattr__(session._header, "seed_length", 1)

    _seed_telemetry_cursor(capture, session)
    capture.capture_session(session)
    assert backend.records == []
