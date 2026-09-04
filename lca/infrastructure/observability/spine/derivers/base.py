# RETAINED(test/CLI/capability; tracking: ADR-0186 PR-3g / I-SESSION-5)
# Production step_tree uses StepTreeFoldDeriver (I-SESSION-5 fold-only builder).
# This Protocol describes on_event for retained test / CLI / capability
# derivers; it is not the EventSpine.subscribe production builder path.

"""Deriver Protocol — derive secondary artefacts from spine events.

A deriver consumes each ``EventRecord`` to produce a derived view
(step-tree, narrative, live tail, ...). Unlike a sink — the destination
of truth — a deriver is best-effort: per FD-2 its exceptions are
contained by the spine and logged on the ``spine.deriver_failed``
channel. Business must never be blocked by a deriver failure.

Production step_tree derivation is Session snapshot / SpineReader +
fold (I-SESSION-5). This Protocol remains for unit tests, CLI replay,
and capability-provided on_event derivers.

The Protocol mirrors the convention used by ``sinks/base.py``:
structural typing via ``runtime_checkable`` so test doubles and
lightweight classes can be used without inheriting from a base class.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lca.infrastructure.observability.spine.event_record import EventRecord


@runtime_checkable
class Deriver(Protocol):
    """A subscriber that derives a secondary artefact from each event."""

    def on_event(self, event: EventRecord) -> None: ...
