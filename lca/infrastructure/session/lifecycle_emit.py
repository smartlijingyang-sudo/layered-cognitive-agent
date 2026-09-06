"""Session lifecycle event production (DSH ↔ LCA spec §5 alignment).

Single production seam for catalog ``@session_event`` facts that must land at
phase boundaries.  All helpers no-op when no Session is bound (tests / offline).
"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass
from typing import Any

from lca.contracts.harness.memory.events import (
    AssistantResponded,
    MessageAccepted,
    ModelCompleted,
    ModelFailed,
    ModelRequested,
    StepEnded,
    StepStarted,
    TurnEnded,
    TurnStarted,
)
from lca.harness.session.emit import emit
from lca.infrastructure.session.bindings import resolve_session_reader
from lca.infrastructure.session.surface_emit import append_user_surface
from lca_kernel.events.fold import SURFACE_ASSISTANT_TYPE

_lifecycle: contextvars.ContextVar[_LifecycleState | None] = contextvars.ContextVar(
    "lca_session_lifecycle",
    default=None,
)


@dataclass
class _LifecycleState:
    turn: int = 1
    open_step: int | None = None
    turn_open: bool = False
    message_accepted: bool = False


def reset_lifecycle(*, turn: int = 1) -> None:
    """Reset per-run lifecycle tracking (call at run bind / fresh run)."""
    _lifecycle.set(_LifecycleState(turn=turn))


def _state() -> _LifecycleState:
    current = _lifecycle.get()
    if current is None:
        current = _LifecycleState()
        _lifecycle.set(current)
    return current


def _session() -> Any | None:
    return resolve_session_reader()


def begin_turn(*, turn: int | None = None, reason: str = "user_input") -> None:
    """``turn.started.v1`` — once per user-driven turn."""
    session = _session()
    if session is None:
        return
    state = _state()
    if turn is not None:
        state.turn = turn
    if state.turn_open:
        return
    emit(session, TurnStarted(turn=state.turn))
    state.turn_open = True


def accept_user_message(
    *,
    message_id: str,
    content: str,
    role: str = "user",
) -> None:
    """``message.accepted.v1`` + durable user surface (DSH user/message)."""
    session = _session()
    if session is None:
        return
    state = _state()
    if state.message_accepted:
        return
    text = content.strip()
    if not text:
        return
    emit(
        session,
        MessageAccepted(message_id=message_id, role=role, content_ref=text),
    )
    append_user_surface(
        session,
        {"role": role, "content": text},
    )
    state.message_accepted = True


def begin_step(*, turn: int | None = None, step: int) -> None:
    """``step.started.v1`` — open one model-request step."""
    session = _session()
    if session is None:
        return
    state = _state()
    turn_no = turn if turn is not None else state.turn
    if state.open_step == step:
        return
    emit(session, StepStarted(turn=turn_no, step=step))
    state.open_step = step


def request_model(
    *,
    turn: int | None = None,
    step: int,
    provider: str,
    model: str,
) -> None:
    """``model.requested.v1`` — immediately before LLM dispatch."""
    session = _session()
    if session is None:
        return
    state = _state()
    turn_no = turn if turn is not None else state.turn
    begin_step(turn=turn_no, step=step)
    emit(
        session,
        ModelRequested(turn=turn_no, step=step, provider=provider, model=model),
    )


def complete_model(
    *,
    turn: int | None = None,
    step: int,
    usage: dict[str, Any] | None = None,
    content: str = "",
    tool_calls: list[dict[str, Any]] | None = None,
) -> None:
    """``model.completed.v1`` + ``assistant.responded.v1`` + assistant surface."""
    session = _session()
    if session is None:
        return
    state = _state()
    turn_no = turn if turn is not None else state.turn
    emit(session, ModelCompleted(turn=turn_no, step=step, usage=usage))
    text = content.strip()
    if text or tool_calls:
        emit(
            session,
            AssistantResponded(
                turn=turn_no,
                step=step,
                content=text,
                tool_calls=tool_calls,
            ),
        )
        if text:
            session.append(
                SURFACE_ASSISTANT_TYPE,
                {"message": {"role": "assistant", "content": text}},
                surface_op="append",
                visibility="model",
            )


def fail_model(*, turn: int | None = None, step: int, error: str) -> None:
    """``model.failed.v1`` — terminal model error for this step."""
    session = _session()
    if session is None:
        return
    state = _state()
    turn_no = turn if turn is not None else state.turn
    emit(session, ModelFailed(turn=turn_no, step=step, error=error))


def end_step(*, turn: int | None = None, step: int) -> None:
    """``step.ended.v1`` — close one step after remember/act cycle."""
    session = _session()
    if session is None:
        return
    state = _state()
    turn_no = turn if turn is not None else state.turn
    if state.open_step != step:
        return
    emit(session, StepEnded(turn=turn_no, step=step))
    state.open_step = None


def end_turn(*, turn: int | None = None, reason: str = "completed") -> None:
    """``turn.ended.v1`` — close the user turn at run terminal."""
    session = _session()
    if session is None:
        return
    state = _state()
    turn_no = turn if turn is not None else state.turn
    if state.open_step is not None:
        end_step(turn=turn_no, step=state.open_step)
    if not state.turn_open:
        return
    emit(session, TurnEnded(turn=turn_no, reason=reason))
    state.turn_open = False
    state.message_accepted = False


__all__ = [
    "accept_user_message",
    "begin_step",
    "begin_turn",
    "complete_model",
    "end_step",
    "end_turn",
    "fail_model",
    "request_model",
    "reset_lifecycle",
]
