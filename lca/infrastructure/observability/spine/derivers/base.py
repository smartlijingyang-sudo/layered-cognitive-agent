# COMPAT(delete-when: PR-9, tracking: ADR-0181)
# 旧 EventSpine deriver；PR-8 shim 走 events/subscribers/spine_* 包装；
# 本模块保留至 PR-9 旧 spine 全退役（rg "lca.plugins.observability.spine.derivers" lca/ = 0 触发）。

"""Deriver Protocol — derive secondary artefacts from spine events.

A deriver is a subscriber to ``EventSpine`` that consumes each
``EventRecord`` to produce a derived view (step-tree, narrative,
live tail, ...). Unlike a sink — the destination of truth — a deriver
is best-effort: per FD-2 its exceptions are contained by the spine
and logged on the ``spine.deriver_failed`` channel. Business must
never be blocked by a deriver failure.

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
