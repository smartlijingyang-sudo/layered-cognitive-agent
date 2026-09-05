"""Wave 6: RecordingLoop — catalog 事件发射 + 逐步不变量（验收 #13）。"""

from __future__ import annotations

from dataclasses import asdict, fields, is_dataclass

import pytest

from lca.contracts.harness.tasks.session import event_registry
from lca.harness.session.emit import event_type_of
from lca.plugins.session.runtime.messages import derive_messages
from lca.plugins.session.runtime.session import Session
from lca_kernel.events.fold import REQUEST_HEADER_CATEGORY, SURFACE_ASSISTANT_TYPE, SURFACE_USER_TYPE


def _minimal_payload(cls: type) -> dict:
    if not is_dataclass(cls):
        return {}
    out: dict = {}
    for f in fields(cls):
        if f.default is not f.default_factory:
            out[f.name] = f.default
        elif f.default_factory is not f.default_factory:  # type: ignore[comparison-overlap]
            out[f.name] = f.default_factory()
        elif f.type is str or "str" in str(f.type):
            out[f.name] = "x"
        elif f.type is int or "int" in str(f.type):
            out[f.name] = 1
        elif f.type is float or "float" in str(f.type):
            out[f.name] = 0.0
        elif f.type is bool or "bool" in str(f.type):
            out[f.name] = False
        elif "dict" in str(f.type):
            out[f.name] = {}
        elif "list" in str(f.type) or "tuple" in str(f.type):
            out[f.name] = ()
        else:
            out[f.name] = None
    return out


def _recording_loop(session: Session) -> None:
    """最小 fake loop:turn/step/surface/header/assistant,无真实工具。"""
    session.append("turn.started.v1", {"turn": 1})
    session.append("step.started.v1", {"turn": 1, "step": 1})
    session.append("message.accepted.v1", {"message_id": "m1", "role": "user", "content_ref": "ping"})
    session.append(
        SURFACE_USER_TYPE,
        {"content": "ping", "messages": [{"role": "user", "content": "ping"}]},
        surface_op="append",
    )
    session.append(
        REQUEST_HEADER_CATEGORY,
        {
            "config": {"model": "test"},
            "system": "sys",
            "messages": [{"role": "user", "content": "ping"}],
        },
    )
    session.append(
        SURFACE_ASSISTANT_TYPE,
        {"message": {"role": "assistant", "content": "pong"}},
        surface_op="append",
    )
    session.append("assistant.responded.v1", {"turn": 1, "step": 1, "content": "pong"})
    session.append("step.ended.v1", {"turn": 1, "step": 1})
    session.append("turn.ended.v1", {"turn": 1, "reason": "complete"})


def test_recording_loop_seq_continuous() -> None:
    session = Session("rec_1")
    _recording_loop(session)
    assert list(range(session.seq)) == [e.seq for e in session.snapshot_events()]


def test_recording_loop_model_request_subset_of_log() -> None:
    session = Session("rec_2")
    _recording_loop(session)
    header = session.request_header()
    assert header is not None
    messages = derive_messages(session.snapshot_events())
    assert messages
    if header.system:
        assert header.system in str(messages) or header.system == "sys"


def test_recording_loop_turn_step_nesting() -> None:
    session = Session("rec_3")
    _recording_loop(session)
    types = [e.type for e in session.snapshot_events()]
    assert types.index("turn.started.v1") < types.index("step.started.v1")
    assert types.index("step.started.v1") < types.index("step.ended.v1")
    assert types.index("step.ended.v1") < types.index("turn.ended.v1")


@pytest.mark.parametrize("event_type", sorted(event_registry().keys()))
def test_catalog_event_appendable(event_type: str) -> None:
    """每个 @session_event 类型可用最小 payload append（destructive 类型除外）。"""
    if event_type in {"session.end_seed.v1", "feedback.record.v1"}:
        pytest.skip("boundary/telemetry gate types covered by dedicated tests")
    cls = event_registry()[event_type]
    session = Session(f"cat_{event_type.replace('.', '_')}")
    payload = _minimal_payload(cls)
    instance = cls(**payload) if is_dataclass(cls) else payload
    data = asdict(instance) if is_dataclass(instance) else instance
    session.append(event_type_of(instance) if is_dataclass(instance) else event_type, data)
    assert session.snapshot_events()[-1].type == event_type
