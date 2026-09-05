"""Wave 4: derive_messages / fork / transcript（验收 #3 / #4）。"""

from __future__ import annotations

import pytest

from lca.plugins.session.runtime.fork import SESSION_END_SEED_TYPE, SessionForkError, fork_session
from lca.plugins.session.runtime.messages import derive_messages, export_transcript
from lca.plugins.session.runtime.session import Session
from lca.plugins.session.runtime.store import SessionStore
from lca_kernel.events.fold import SURFACE_ASSISTANT_TYPE, SURFACE_USER_TYPE


def _surface_user(seq: int, content: str) -> dict:
    return {
        "type": SURFACE_USER_TYPE,
        "seq": seq,
        "time": seq,
        "data": {"content": content},
        "surfaceOp": "append",
    }


def _surface_assistant(seq: int, content: str) -> dict:
    return {
        "type": SURFACE_ASSISTANT_TYPE,
        "seq": seq,
        "time": seq,
        "data": {"message": {"role": "assistant", "content": content}},
        "surfaceOp": "append",
    }


def test_derive_messages_matches_surface_replay() -> None:
    events = [_surface_user(0, "hi"), _surface_assistant(1, "hello")]
    assert derive_messages(events) == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]


def test_session_derive_messages_incremental() -> None:
    session = Session("s_derive")
    session.append(
        SURFACE_USER_TYPE,
        {"content": "q"},
        surface_op="append",
    )
    session.append(
        SURFACE_ASSISTANT_TYPE,
        {"message": {"role": "assistant", "content": "a"}},
        surface_op="append",
    )
    assert session.derive_messages() == [
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": "a"},
    ]


def test_fork_child_derive_messages_match_prefix() -> None:
    store = SessionStore()
    parent = store.create("parent")
    parent.append("turn.started.v1", {"turn": 1})
    parent.append(
        SURFACE_USER_TYPE,
        {"content": "one"},
        surface_op="append",
    )
    parent.append("turn.ended.v1", {"turn": 1, "reason": "done"})
    parent.append("turn.started.v1", {"turn": 2})
    parent.append(
        SURFACE_USER_TYPE,
        {"content": "two"},
        surface_op="append",
    )
    parent.append("turn.ended.v1", {"turn": 2, "reason": "done"})
    child = fork_session(store, parent, boundary=2, child_session_id="child")
    assert child.header.parent_session == "parent"
    assert child.header.is_seeded is True
    assert child.event_at(child.seq - 1).type == SESSION_END_SEED_TYPE  # type: ignore[union-attr]
    assert derive_messages(child.snapshot_events()) == derive_messages(parent.snapshot_events(0, 3))


def test_fork_open_turn_rejected() -> None:
    store = SessionStore()
    parent = store.create("p2")
    parent.append("turn.started.v1", {"turn": 1})
    parent.append(
        SURFACE_USER_TYPE,
        {"content": "x"},
        surface_op="append",
    )
    with pytest.raises(SessionForkError) as exc_info:
        fork_session(store, parent, boundary=1)
    assert exc_info.value.code == "OPEN_TURN"


def test_transcript_skips_replacement_copies() -> None:
    events = [
        _surface_user(0, "a"),
        {
            "type": SURFACE_ASSISTANT_TYPE,
            "seq": 1,
            "time": 1,
            "data": {"message": {"role": "assistant", "content": "old"}},
            "surfaceOp": "append",
        },
        {
            "type": SURFACE_ASSISTANT_TYPE,
            "seq": 2,
            "time": 2,
            "data": {"message": {"role": "assistant", "content": "new"}},
            "surfaceOp": {"op": "replace", "start": 1, "end": 1},
            "sourceEventSeqs": [1],
        },
    ]
    assert export_transcript(events) == [{"role": "user", "content": "a"}]
