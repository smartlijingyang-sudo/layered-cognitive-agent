"""Observer implementations — translate :class:`GraphObservation` to spine.

The kernel never imports this module. Wiring (``PlanInterpreterAdapter
.__post_init__``) decides which observer runs: a no-op for unit
tests, a recording fake for table-driven assertions, a spine-backed
observer for production runs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from lca.framework.graph.ep_table import GraphEpTable, default_graph_ep_table
from lca.framework.graph.observation import (
    EmitFn,
    GraphObservation,
    payload_of,
)

log = logging.getLogger(__name__)


@dataclass
class RecordingObserver:
    """In-memory observer. Tests assert against ``.events``.

    Lives next to the spine observer (same module) so wiring code
    has one import for both. It implements the same Protocol so the
    kernel cannot tell the difference at runtime.
    """

    events: list[GraphObservation] = field(default_factory=list)

    def observe(self, event: GraphObservation) -> None:
        self.events.append(event)

    def clear(self) -> None:
        self.events.clear()

    def by_kind(self, kind: str) -> tuple[GraphObservation, ...]:
        return tuple(e for e in self.events if e.kind == kind)


@dataclass
class SpineGraphObserver:
    """Translate observations into spine EP events.

    The observer owns no I/O — it calls the injected ``emit`` callable
    with ``(execution_point, payload)``. Wiring supplies ``emit``;
    unit tests supply a list-appending callable; production wiring
    supplies the ``_safe_append`` seam so failures stay contained.
    """

    ep_table: GraphEpTable = field(default_factory=default_graph_ep_table)
    emit: EmitFn | None = None

    def observe(self, event: GraphObservation) -> None:
        if self.emit is None:
            return
        try:
            ep = self.ep_table.resolve(event.kind)
        except KeyError:
            log.warning(
                "spine_observer: unknown kind=%s; dropping event",
                event.kind,
                exc_info=True,
            )
            return
        try:
            self.emit(ep, payload_of(event))
        except Exception:
            log.warning(
                "spine_observer: emit failed kind=%s ep=%s",
                event.kind,
                ep,
                exc_info=True,
            )


def emit_from_safe_append(
    safe_append: Any,
    *,
    spine: Any | None,
    channel: str = "control",
    outcome: Any = None,
) -> EmitFn:
    """Adapt the ``_safe_append`` seam to the observer's EmitFn shape.

    The wiring layer owns this glue so the observer stays decoupled
    from the spine import graph. ``safe_append`` is a partial or
    lambda positioned on the existing
    :func:`lca.harness.declarative.compile.instrument.wrap._safe_append`.
    """

    def emit(ep: str, payload: dict[str, Any]) -> None:
        safe_append(
            spine=spine,
            execution_point=ep,
            channel=channel,
            payload=payload,
            outcome=outcome,
            span=None,
        )

    return emit


__all__ = [
    "RecordingObserver",
    "SpineGraphObserver",
    "emit_from_safe_append",
]
