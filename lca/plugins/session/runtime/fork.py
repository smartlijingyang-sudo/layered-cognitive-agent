"""Session fork —— 截断 prefix 开 child session（DSH SessionStore.fork 对位）。"""

from __future__ import annotations

import time

from lca.plugins.session.runtime.session import Session
from lca.plugins.session.runtime.store import SessionStore
from lca_kernel.events.session import SESSION_FORMAT_VERSION, SessionHeader

__all__ = [
    "SESSION_END_SEED_TYPE",
    "SessionForkError",
    "fork_session",
]

SESSION_END_SEED_TYPE = "session.end_seed.v1"


class SessionForkError(ValueError):
    """Fork 拒绝码（对齐 DSH SessionForkError 语义）。"""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


def fork_session(
    store: SessionStore,
    source: Session | str,
    boundary: int | None = None,
    *,
    child_session_id: str | None = None,
) -> Session:
    """Inclusive boundary 截断 live session,开 seeded child + ``session.end_seed.v1``。"""
    if isinstance(source, Session):
        live = store.get(source.id)
        if live is None:
            raise SessionForkError(f'session "{source.id}" not found', code="SESSION_NOT_FOUND")
        if live is not source:
            raise SessionForkError(
                f'session "{source.id}" is not live in store',
                code="SESSION_NOT_LIVE",
            )
    else:
        live = store.get(source)
        if live is None:
            raise SessionForkError(f'session "{source}" not found', code="SESSION_NOT_FOUND")

    last_seq = live.seq - 1 if live.seq > 0 else None
    if boundary is None:
        boundary = last_seq if last_seq is not None else -1
    elif boundary < 0 or (last_seq is not None and boundary > last_seq):
        raise SessionForkError(
            f"fork boundary {boundary} invalid for session {live.id!r}",
            code="INVALID_BOUNDARY",
        )

    if boundary >= 0:
        seed_events = live.snapshot_events(0, boundary + 1)
        _assert_boundary_not_in_open_turn(seed_events, boundary, live.id)
    else:
        seed_events = ()

    if child_session_id is not None and store.get(child_session_id) is not None:
        raise SessionForkError(
            f'session "{child_session_id}" already exists',
            code="SESSION_ALREADY_EXISTS",
        )

    if child_session_id is None:
        placeholder = store.create()
        child_session_id = placeholder.id
        store.dispose(child_session_id)

    header = SessionHeader(
        version=SESSION_FORMAT_VERSION,
        id=child_session_id,
        created_at=int(time.time() * 1000),
        parent_session=live.id,
        seed_length=len(seed_events),
        is_seeded=True,
    )
    child = store.restore(child_session_id, header, seed_events)
    if seed_events:
        last = child.event_at(child.seq - 1)
        if last is None or last.type != SESSION_END_SEED_TYPE:
            child.append(SESSION_END_SEED_TYPE, {})
    return child


def _assert_boundary_not_in_open_turn(events: tuple, boundary: int, session_id: str) -> None:
    last_turn_boundary = None
    for event in events:
        if event.type in ("turn.started.v1", "turn.ended.v1", "turn/start", "turn/end"):
            last_turn_boundary = event
    if last_turn_boundary is not None and last_turn_boundary.type in (
        "turn.started.v1",
        "turn/start",
    ):
        turn = last_turn_boundary.data.get("turn")
        raise SessionForkError(
            f"fork boundary {boundary} in session {session_id!r} ends inside open turn {turn}",
            code="OPEN_TURN",
        )
