"""Session lifecycle event production (DSH ↔ LCA spec §5 alignment).

Single production seam for catalog ``@session_event`` facts that must land at
phase boundaries.  All helpers no-op when no Session is bound (tests / offline).
"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass
from typing import Any

from lca.contracts.harness.collaboration.agent import LiveAgentStatus
from lca.contracts.harness.memory.events import (
    ApprovalPersisted,
    AssistantResponded,
    MessageAccepted,
    ModelCompleted,
    ModelFailed,
    ModelRequested,
    SessionCheckpoint,
    SessionCreated,
    StepEnded,
    StepStarted,
    ThinkingCompleted,
    ThinkingDelta,
    TurnEnded,
    TurnStarted,
)
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.result import Result
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
    approval_pause_emitted: bool = False


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


def create_session(profile: str, preset: str | None = None) -> SessionCreated | None:
    """``session.created.v1`` — once when a run Session is bound."""
    session = _session()
    if session is None:
        return None
    event = SessionCreated(profile=profile, preset=preset)
    emit(session, event)
    return event


def checkpoint(status: str) -> SessionCheckpoint | None:
    """``session.checkpoint.v1`` — lifecycle recovery authority (no ``working``)."""
    if status == LiveAgentStatus.WORKING.value:
        raise ValueError("working state must not be checkpointed")
    session = _session()
    if session is None:
        return None
    event = SessionCheckpoint(status=status)
    emit(session, event)
    return event


def persist_approval(approval_id: str, resume_point: dict[str, object]) -> ApprovalPersisted | None:
    """``approval.persisted.v1`` — durable declarative resume point."""
    session = _session()
    if session is None:
        return None
    state = _state()
    if state.approval_pause_emitted:
        return None
    event = ApprovalPersisted(approval_id=approval_id, resume_point=resume_point)
    emit(session, event)
    state.approval_pause_emitted = True
    return event


def emit_approval_pause_from_result(result: Result) -> None:
    """Emit ``approval.persisted.v1`` + ``waiting_input`` checkpoint from carrier ``extra``."""
    if result.status is not TaskStatus.INPUT_REQUIRED:
        return
    state = _state()
    if state.approval_pause_emitted:
        return
    extra = result.extra or {}
    approval_request = extra.get("approval_request")
    state_snapshot = extra.get("state_snapshot")
    if not isinstance(approval_request, dict) or state_snapshot is None:
        return
    approval_id = approval_request.get("approval_id")
    if not isinstance(approval_id, str) or not approval_id:
        return
    from lca.plugins.session.runtime.resume_point import (
        resume_point_from_state_snapshot,
        serialize_resume_point,
    )

    resume_point = serialize_resume_point(
        resume_point_from_state_snapshot(approval_id, state_snapshot),
    )
    persist_approval(approval_id, resume_point)
    checkpoint(LiveAgentStatus.WAITING_INPUT.value)


def terminal_checkpoint_status(status: TaskStatus) -> str | None:
    """Map a terminal carrier status to ``session.checkpoint.v1`` wire value."""
    mapping = {
        TaskStatus.COMPLETED: "completed",
        TaskStatus.FAILED: "failed",
        TaskStatus.CANCELED: "canceled",
    }
    return mapping.get(status)


def session_append_for_thinking() -> Any:
    """Return a ``SessionAppend`` hook that mirrors thinking.* via harness emit.

    No-op when no Session is bound (tests / offline). Accepts
    ``ThinkingDelta`` / ``ThinkingCompleted`` payloads from
    :class:`TelemetryLLMAdapter`.
    """

    def _append(payload: Any) -> None:
        session = _session()
        if session is None:
            return
        if isinstance(payload, (ThinkingDelta, ThinkingCompleted)):
            emit(session, payload)

    return _append


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


def resolve_run_session_writer(run_session: Any) -> Any | None:
    """Return the DSH Session writer for a transport ``RunSession`` when bound."""
    bound = getattr(run_session, "event_session", None)
    if bound is None:
        return _session()
    bridge = getattr(bound, "bridge", None)
    if bridge is not None:
        inner = getattr(bridge, "inner", None)
        if inner is not None:
            return inner
    return _session()


def emit_run_attachments(
    run_session: Any,
    attachment_ids: tuple[str, ...],
    *,
    file_store: Any,
) -> None:
    """``attachment.committed.v1`` for each run-bound attachment at session build."""
    if not attachment_ids:
        return
    import contextlib

    from lca.infrastructure.observability.meta_event_emit import emit_attachment_committed

    writer = resolve_run_session_writer(run_session)
    get_meta = getattr(file_store, "get", None)
    if not callable(get_meta):
        return
    for attachment_id in attachment_ids:
        meta = None
        with contextlib.suppress(Exception):
            meta = get_meta(attachment_id)
        if meta is None:
            continue
        emit_attachment_committed(
            attachment_id=str(getattr(meta, "attachment_id", attachment_id)),
            name=str(getattr(meta, "name", attachment_id)),
            size_bytes=int(getattr(meta, "size_bytes", 0) or 0),
            mime_type=str(getattr(meta, "mime_type", "") or "application/octet-stream"),
            session=writer,
        )


__all__ = [
    "accept_user_message",
    "begin_step",
    "begin_turn",
    "checkpoint",
    "complete_model",
    "create_session",
    "emit_approval_pause_from_result",
    "emit_run_attachments",
    "end_step",
    "end_turn",
    "fail_model",
    "persist_approval",
    "request_model",
    "reset_lifecycle",
    "resolve_run_session_writer",
    "session_append_for_thinking",
    "terminal_checkpoint_status",
]
