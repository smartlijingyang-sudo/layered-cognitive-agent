"""EventSpine — single entrypoint for emitting events (I4 / I5).

All callers go through ``spine.append(...)``. Direct calls to legacy
``RunStore.append`` etc. are forbidden at runtime by I4.

ADR-0183 PR-9: the write implementation is collapsed into
``loop_cursor._spine_port.spine_port_append``; this class keeps assembly
(sinks / subscribers), ``subscribe`` and ``flush`` / ``close`` lifecycle,
and forwards ``append`` to the single port.

FD-1 sink errors propagate to caller (fail-fast).
FD-2 deriver errors are contained: a logged spine.deriver_failed event
       is emitted; the original event still reaches the sink.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from datetime import datetime
from typing import Any

from lca.infrastructure.observability.loop_cursor._spine_port import spine_port_append
from lca.infrastructure.observability.spine.context import SpineContext
from lca.infrastructure.observability.spine.event_record import (
    Channel,
    EventRecord,
    Outcome,
    Phase,
)
from lca.infrastructure.observability.spine.sinks.base import EventSink


class EventSpine:
    """The single append-only entrypoint for framework events."""

    def __init__(
        self,
        sinks: list[EventSink],
        *,
        subscribers: list[Callable[[EventRecord], None]] | None = None,
        run_id: str | None = None,
    ) -> None:
        if not sinks:
            raise ValueError("EventSpine requires at least one sink")
        self._sinks = sinks
        self._subscribers = list(subscribers or [])
        if run_id is not None:
            SpineContext.set_run(run_id)

    def subscribe(self, fn: Callable[[EventRecord], None]) -> Callable[[], None]:
        """Register a deriver / callback. Returns disposer."""
        self._subscribers.append(fn)

        def _dispose() -> None:
            with suppress(ValueError):
                self._subscribers.remove(fn)

        return _dispose

    def append(
        self,
        *,
        execution_point: str,
        channel: Channel,
        caller_payload: dict[str, Any] | None = None,
        outcome: Outcome | None = None,
        span_ctx: Any | None = None,
        phase: Phase = "live",
        reason: str | None = None,
        when: datetime | None = None,
    ) -> EventRecord:
        """Façade — forward to ``spine_port_append``, the single write impl.

        Signature and failure semantics (FD-1 / FD-2) are unchanged; the
        implementation lives in ``loop_cursor._spine_port`` (ADR-0183 PR-9).
        """
        return spine_port_append(
            self._sinks,
            self._subscribers,
            execution_point=execution_point,
            channel=channel,
            caller_payload=caller_payload,
            outcome=outcome,
            span_ctx=span_ctx,
            phase=phase,
            reason=reason,
            when=when,
        )

    def flush(self) -> None:
        for sink in self._sinks:
            close = getattr(sink, "flush", None)
            if callable(close):
                close()

    def close(self) -> None:
        for sink in self._sinks:
            sink.close()
