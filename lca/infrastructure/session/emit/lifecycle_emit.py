"""Session lifecycle event production (DSH ↔ LCA spec §5 alignment).

Single production seam for catalog ``@session_event`` facts that must land at
phase boundaries.  All helpers no-op when no Session is bound (tests / offline).
Idempotency is delegated to the Session append-only log + Reducer contract
(spec §H; pre-T4 `_LifecycleState` ContextVar is gone).
"""

from __future__ import annotations

from typing import Any

from lca.contracts.harness.collaboration.agent import LiveAgentStatus
from lca.contracts.harness.memory.events import (
    ApprovalPersisted,
    AssistantResponded,
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
from lca.contracts.models.core.execution.result import Result
from lca.contracts.models.core.state.lifecycle import TaskStatus
from lca.infrastructure.session.bindings import resolve_session_reader
from lca.loop.fact_gateway import append_catalog_bound

_LIFECYCLE_ACTOR = "lifecycle"


def _session() -> Any | None:
    return resolve_session_reader()


def _append_catalog(event: Any) -> bool:
    """Append one catalog fact via FactGateway; False when session unbound."""
    return append_catalog_bound(event, actor=_LIFECYCLE_ACTOR) is not None


def begin_turn(*, turn: int | None = None, reason: str = "user_input") -> None:
    """``turn.started.v1`` — once per user-driven turn."""
    if _session() is None:
        return
    _append_catalog(TurnStarted(turn=turn or 1))


def begin_step(*, turn: int | None = None, step: int) -> None:
    """``step.started.v1`` — open one model-request step."""
    if _session() is None:
        return
    turn_no = turn if turn is not None else 1
    _append_catalog(StepStarted(turn=turn_no, step=step))


def request_model(
    *,
    turn: int | None = None,
    step: int,
    provider: str,
    model: str,
) -> None:
    """``model.requested.v1`` — immediately before LLM dispatch."""
    if _session() is None:
        return
    turn_no = turn if turn is not None else 1
    begin_step(turn=turn_no, step=step)
    _append_catalog(
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
    """``model.completed.v1`` + ``assistant.responded.v1`` (catalog-only).

    Surface event (``surface/assistant_message``) is appended separately by
    :meth:`RunSessionWriter.append_assistant_message` — see
    :func:`lca.plugins.events.hooks.model_visible.adapter._emit_lifecycle_post`.
    """
    if _session() is None:
        return
    turn_no = turn if turn is not None else 1
    _append_catalog(ModelCompleted(turn=turn_no, step=step, usage=usage))
    text = content.strip()
    if text or tool_calls:
        _append_catalog(
            AssistantResponded(
                turn=turn_no,
                step=step,
                content=text,
                tool_calls=tool_calls,
            ),
        )


def fail_model(*, turn: int | None = None, step: int, error: str) -> None:
    """``model.failed.v1`` — terminal model error for this step."""
    if _session() is None:
        return
    turn_no = turn if turn is not None else 1
    _append_catalog(ModelFailed(turn=turn_no, step=step, error=error))


def create_session(profile: str, preset: str | None = None) -> SessionCreated | None:
    """``session.created.v1`` — once when a run Session is bound."""
    if _session() is None:
        return None
    event = SessionCreated(profile=profile, preset=preset)
    _append_catalog(event)
    return event


def checkpoint(
    status: str,
    *,
    pending_tools_calling: list[dict[str, Any]] | None = None,
) -> SessionCheckpoint | None:
    """``session.checkpoint.v1`` — lifecycle recovery authority (no ``working``)."""
    if status == LiveAgentStatus.WORKING.value:
        raise ValueError("working state must not be checkpointed")
    if _session() is None:
        return None
    event = SessionCheckpoint(
        status=status,
        pending_tools_calling=pending_tools_calling,
    )
    _append_catalog(event)
    return event


def persist_approval(approval_id: str, resume_point: dict[str, object]) -> ApprovalPersisted | None:
    """``approval.persisted.v1`` — durable declarative resume point."""
    if _session() is None:
        return None
    event = ApprovalPersisted(approval_id=approval_id, resume_point=resume_point)
    _append_catalog(event)
    return event


def emit_approval_pause_from_result(result: Result) -> None:
    """Emit ``approval.persisted.v1`` + ``waiting_input`` checkpoint from carrier ``extra``.

    The paused decision's tool calls are recorded as ``step.tool_call.record``
    facts marked ``status="pending_approval"`` before the checkpoint, so the
    gateway wire publishes ``tools_calling`` (the UI card) ahead of the
    ``step_start{human_approval}`` pause pair. ``askUserQuestion`` arguments
    gain ``lca_run_id`` so the frontend submit handler can resume the run.
    """
    if result.status is not TaskStatus.INPUT_REQUIRED:
        return
    extra = result.extra or {}
    approval_request = extra.get("approval_request")
    state_snapshot = extra.get("state_snapshot")
    if not isinstance(approval_request, dict) or state_snapshot is None:
        return
    approval_id = approval_request.get("approval_id")
    if not isinstance(approval_id, str) or not approval_id:
        return
    from lca.infrastructure.observability.facade.run.context import (
        get_current_run_scope,
    )
    from lca.loop.commit.tool_journal import record_step_tool_call
    from lca.plugins.session.runtime.resume.point import (
        resume_point_from_state_snapshot,
        serialize_resume_point,
    )

    scope = get_current_run_scope()
    run_id = str(scope.run_id) if scope is not None and scope.run_id else ""
    pending: list[dict[str, Any]] = []
    tool_calls = approval_request.get("tool_calls")
    if isinstance(tool_calls, list):
        for call in tool_calls:
            if not isinstance(call, dict):
                continue
            tool_name = str(call.get("tool_name") or "")
            call_id = str(call.get("call_id") or "")
            if not tool_name or not call_id:
                continue
            arguments = call.get("arguments")
            if isinstance(arguments, dict) and tool_name == "askUserQuestion" and run_id:
                arguments = {**arguments, "lca_run_id": run_id}
            args = arguments if isinstance(arguments, dict) else {}
            record_step_tool_call(
                tool_name=tool_name,
                invocation_id=call_id,
                arguments=args,
                status="pending_approval",
                actor=_LIFECYCLE_ACTOR,
            )
            pending.append(
                {
                    "tool_name": tool_name,
                    "call_id": call_id,
                    "arguments": args,
                }
            )
    resume_point = serialize_resume_point(
        resume_point_from_state_snapshot(approval_id, state_snapshot),
    )
    persist_approval(approval_id, resume_point)
    checkpoint(
        LiveAgentStatus.WAITING_INPUT.value,
        pending_tools_calling=pending or None,
    )


def terminal_checkpoint_status(status: TaskStatus) -> str | None:
    """Map a terminal carrier status to ``session.checkpoint.v1`` wire value."""
    mapping = {
        TaskStatus.COMPLETED: "completed",
        TaskStatus.FAILED: "failed",
        TaskStatus.CANCELED: "canceled",
    }
    return mapping.get(status)


def session_append_for_thinking() -> Any:
    """Return a ``SessionAppend`` hook that mirrors thinking.* via FactGateway.

    No-op when no Session is bound (tests / offline). Accepts
    ``ThinkingDelta`` / ``ThinkingCompleted`` payloads from
    :class:`TelemetryLLMAdapter`.
    """

    def _append(payload: Any) -> None:
        if isinstance(payload, (ThinkingDelta, ThinkingCompleted)):
            _append_catalog(payload)

    return _append


def end_step(*, turn: int | None = None, step: int) -> None:
    """``step.ended.v1`` — close one step after remember/act cycle."""
    if _session() is None:
        return
    turn_no = turn if turn is not None else 1
    _append_catalog(StepEnded(turn=turn_no, step=step))


def end_turn(*, turn: int | None = None, reason: str = "completed") -> None:
    """``turn.ended.v1`` — close the user turn at run terminal."""
    if _session() is None:
        return
    turn_no = turn if turn is not None else 1
    _append_catalog(TurnEnded(turn=turn_no, reason=reason))


def reset_lifecycle(*, turn: int = 1) -> None:
    """Compatibility no-op for pre-T4 reset hooks (state ContextVar removed)."""
    del turn


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
