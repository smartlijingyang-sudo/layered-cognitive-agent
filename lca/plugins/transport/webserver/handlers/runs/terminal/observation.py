"""Carrier-side terminal observation — Session facts when agent path did not close the run.

``AgentRunFinished`` remains owned by :mod:`lca.agent.cognitive_agent`. When the
lifecycle coordinator observes failure before that finally block runs, we
emit a ``RuntimeObserved`` terminal fact so SSE / live tail consumers
receive an explicit failure signal (SSOT via ``Session.append``,
no journal fallback).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from lca.contracts.models.observability.event.event import OperationOutcome, RuntimeKind
from lca.contracts.models.observability.journal.journal import (
    AgentRunFinished,
    JournalEvent,
    RuntimeObserved,
    StampedEvent,
    TeamRunFinished,
)
from lca.contracts.observability.registry.status import RunLifecycleStatus
from lca.infrastructure.observability import record

if TYPE_CHECKING:
    from lca.plugins.transport.webserver.handlers.runs.session.session.session import (
        RunSession,
    )

_log = structlog.get_logger(__name__)

_TERMINAL_EVENT_TYPES = (AgentRunFinished, TeamRunFinished)
_CARRIER_TERMINAL_OPERATION = "run.lifecycle.failed"


def _resolve_session_inner(session: RunSession) -> Any:
    """Resolve the bound run Session from ``RunSession.event_session``.

    Accepts ``RunEventSessionBridge`` directly or a ``BoundRunEventSession``
    (which exposes ``.bridge``).
    """
    obj = getattr(session, "event_session", None)
    if obj is None:
        return None
    inner = getattr(obj, "inner", None)
    if inner is not None and not callable(inner):
        return inner
    bridge = getattr(obj, "bridge", None)
    if bridge is not None:
        return getattr(bridge, "inner", None)
    return None


def journal_has_terminal_event(session: RunSession) -> bool:
    """Return whether the Session already records a terminal container event."""
    inner = _resolve_session_inner(session)
    if inner is None:
        return False
    return any(
        event.type in {"AgentRunFinished", "TeamRunFinished"}
        for event in inner.snapshot_events()
    )


def emit_carrier_run_failed(
    session: RunSession,
    *,
    user_message: str,
    exception_class: str = "",
    err_kind: str = "unknown",
    status: str = "",
) -> StampedEvent | None:
    """Append ``RuntimeObserved(run.lifecycle.failed)`` to Session (SSOT only)."""
    if not user_message.strip():
        return None
    if journal_has_terminal_event(session):
        return None
    wire_status = status.strip() or RunLifecycleStatus.FAILED.value
    return record(
        RuntimeObserved(
            kind=RuntimeKind.ERROR,
            operation=_CARRIER_TERMINAL_OPERATION,
            source="lifecycle.coordinator",
            outcome=OperationOutcome.ERROR,
            error_message=user_message,
            attributes={
                "run_id": session.run_id,
                "trace_id": session.trace_id,
                "exception_class": exception_class,
                "err_kind": err_kind,
                "status": wire_status,
            },
        )
    )


def ensure_carrier_terminal_observation(session: RunSession) -> StampedEvent | None:
    """Best-effort terminal fact before hub close when the run failed without ``AgentRunFinished``."""
    failed = session.status in {RunLifecycleStatus.FAILED, RunLifecycleStatus.CANCELED}
    if not failed:
        return None
    if journal_has_terminal_event(session):
        return None
    message = session.error or "run failed"
    wire_status = session.status.value if hasattr(session.status, "value") else str(session.status)
    return emit_carrier_run_failed(
        session,
        user_message=message,
        exception_class=_exception_class_from_message(message),
        status=wire_status,
    )


def _exception_class_from_message(message: str) -> str:
    head = message.split(":", 1)[0].strip()
    if head and head[0].isupper():
        return head
    return ""


def is_carrier_terminal_observed(event: JournalEvent) -> bool:
    """True when *event* is the carrier terminal observation fact."""
    return (
        isinstance(event, RuntimeObserved)
        and event.operation == _CARRIER_TERMINAL_OPERATION
        and event.kind is RuntimeKind.ERROR
    )


__all__ = [
    "emit_carrier_run_failed",
    "ensure_carrier_terminal_observation",
    "is_carrier_terminal_observed",
    "journal_has_terminal_event",
]
