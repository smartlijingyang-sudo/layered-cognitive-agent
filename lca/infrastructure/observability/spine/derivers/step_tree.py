"""StepTreeDeriver — wraps ``StepGroupedBackend`` as a spine deriver (Task 2.2).

PR-2 parallel-write phase: the deriver exists alongside the legacy backend
and is subscribed to ``EventSpine`` so the framework has a structural
hook for the eventual spine-native step-tree projection.  For now the
deriver delegates per-event work to the wrapped backend's deprecated
``write(event)`` path (which is a no-op + warning) and exposes ``flush()``
so terminalizer code can drive an identical disk write as the legacy
backend.  Future PR-3 work will replace the wrap with native EventRecord
reconstruction.

The deriver does NOT remove or redirect any existing call site: both
legacy ``StepGroupedBackend`` instances and ``StepTreeDeriver`` instances
write their own ``journal.json`` independently when ``flush()`` is called.
"""

from __future__ import annotations

import logging
from typing import Any

from lca.infrastructure.observability.journal.step.backend import StepGroupedBackend
from lca.infrastructure.observability.spine.derivers.base import Deriver
from lca.infrastructure.observability.spine.event_record import EventRecord

log = logging.getLogger(__name__)


class StepTreeDeriver(Deriver):
    """Deriver that delegates to a wrapped ``StepGroupedBackend``.

    The wrapped backend owns the lifecycle store reference and the
    on-disk ``journal.json`` path.  ``on_event`` forwards to
    ``backend.write(event)`` so the legacy no-op path stays exercised
    during parallel-write; ``flush`` triggers the actual ``journal.json``
    write through the same projector the legacy backend uses.
    """

    def __init__(self, backend: StepGroupedBackend) -> None:
        self._backend = backend

    @property
    def backend(self) -> StepGroupedBackend:
        """Wrapped backend (test seam + boot wiring convenience)."""
        return self._backend

    def on_event(self, event: EventRecord) -> None:
        """Forward a spine event into the legacy backend's write path.

        The legacy ``StepGroupedBackend.write`` is deprecated and a no-op
        (logs a warning pointing callers at ``step_lifecycle.*`` facade).
        Forwarding keeps the wrap contractually honest: every event the
        spine produces still reaches the backend's surface.

        Orphan events (``phase="orphan"``) are skipped — they have no
        step to attach to, must not enter the step-tree projection, and
        are still visible via the append-only ``events.jsonl`` sink
        (ADR-0165.1 §19, PR-6).
        """
        if event.phase != "live":
            return
        try:
            self._backend.write(_wrap(event))  # type: ignore[arg-type]
        except Exception as exc:
            # FD-2 already contains spine subscribers, but derivers may
            # also be invoked directly (e.g. tests).  Never propagate.
            log.warning(
                "step_tree_deriver.on_event failed execution_point=%s err=%s",
                event.execution_point,
                exc,
                exc_info=True,
            )

    def flush(self) -> None:
        """Write ``journal.json`` via the wrapped backend's projector.

        Idempotent w.r.t. the lifecycle store's document state: a doc
        without ``closed_at`` is a no-op (matches legacy semantics in
        ``StepGroupedBackend.flush``).
        """
        self._backend.flush()


def _wrap(event: EventRecord) -> Any:
    """Build the smallest legacy-shape event the backend's write path accepts.

    The actual ``StepGroupedBackend.write`` is a deprecated no-op, so the
    payload contents do not affect disk state.  We just need an object
    that survives ``type(event).__name__`` (used in the deprecation log)
    and duck-types a ``JournalEvent`` instance.
    """
    from lca.contracts.models.observability.journal import RuntimeObserved

    return RuntimeObserved(
        operation=event.execution_point,
        source="spine",
        attributes={"sequence": event.sequence, "span_id": event.span_id},
    )


__all__ = ["StepTreeDeriver"]
