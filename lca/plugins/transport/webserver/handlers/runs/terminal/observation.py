"""Carrier-side terminal observation — Journal facts when agent path did not close the run.

``AgentRunFinished`` remains owned by :mod:`lca.agent.cognitive_agent`. When the
lifecycle coordinator observes failure before that finally block runs (or when
``record()`` was unbound), we emit a ``RuntimeObserved`` terminal fact so SSE /
live tail consumers receive an explicit failure signal.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

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
from lca.plugins.transport.webserver.handlers.runs.terminal.status.status import (
    journal_store,
)

if TYPE_CHECKING:
    from lca.infrastructure.observability import BoundObservability
    from lca.plugins.transport.webserver.handlers.runs.session.session.session import (
        RunSession,
    )

_log = structlog.get_logger(__name__)

_TERMINAL_EVENT_TYPES = (AgentRunFinished, TeamRunFinished)
_CARRIER_TERMINAL_OPERATION = "run.lifecycle.failed"


def journal_has_terminal_event(session: RunSession) -> bool:
    """Return whether the run journal already records a terminal container event."""
    hub = session.hub
    if hub is None:
        return False
    store = journal_store(hub)
    if store is None:
        return False
    return any(isinstance(stamped.event, _TERMINAL_EVENT_TYPES) for stamped in store.events)


def emit_carrier_run_failed(
    session: RunSession,
    *,
    hub: BoundObservability | None,
    user_message: str,
    exception_class: str = "",
    err_kind: str = "unknown",
    status: str = "",
) -> StampedEvent | None:
    """Append ``RuntimeObserved(run.lifecycle.failed)`` when no terminal journal fact exists."""
    if not user_message.strip():
        return None
    if journal_has_terminal_event(session):
        return None
    if hub is None or hub.journal is None:
        return None
    wire_status = status.strip() or RunLifecycleStatus.FAILED.value
    return hub.journal.write(
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
    from lca.infrastructure.observability import fold_run_state

    folded = None
    store = journal_store(session.hub) if session.hub is not None else None
    if store is not None:
        folded = fold_run_state(store.events)
    failed = (
        session.status in {RunLifecycleStatus.FAILED, RunLifecycleStatus.CANCELED}
        or (folded is not None and folded.status in {RunLifecycleStatus.FAILED, RunLifecycleStatus.CANCELED})
    )
    if not failed:
        return None
    if journal_has_terminal_event(session):
        return None
    message = (folded.error if folded is not None and folded.error else None) or session.error or "run failed"
    wire_status = session.status.value if hasattr(session.status, "value") else str(session.status)
    return emit_carrier_run_failed(
        session,
        hub=session.hub,
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
