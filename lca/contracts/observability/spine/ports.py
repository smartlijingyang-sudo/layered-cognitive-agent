"""Spine port contracts — ``EventSpine`` protocol.

``EventSpine`` is the append-only event port every emitter talks to.
The concrete implementation lives in
:mod:`lca.infrastructure.observability.spine.event.spine`; harness and
other contract-only layers depend on this ``Protocol`` instead of the
implementation.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from lca.contracts.observability.spine.context import SpanContext
from lca.contracts.observability.spine.records import Channel, Outcome

__all__ = ["EventSpine"]


@runtime_checkable
class EventSpine(Protocol):
    """Port for the append-only spine event sink (I4 / I5)."""

    def append(
        self,
        *,
        execution_point: str,
        channel: Channel,
        caller_payload: dict[str, Any] | None = None,
        outcome: Outcome | None = None,
        span_ctx: SpanContext | None = None,
        phase: str = "live",
        reason: str | None = None,
        when: datetime | None = None,
    ) -> Any:
        """Append one spine event and return the sealed record."""
        ...

    def subscribe(self, fn: Callable[[Any], None]) -> Callable[[], None]:
        """Register a deriver / callback. Returns disposer."""
        ...

    def flush(self) -> None: ...
    def close(self) -> None: ...
