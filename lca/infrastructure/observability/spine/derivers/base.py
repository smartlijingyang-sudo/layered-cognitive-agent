# COMPAT(delete-when: ADR-0186 PR-3g 全部 Deriver.on_event 路径迁完且实现清零,
#        tracking: ADR-0186 PR-3g / I-SESSION-5)
# Deriver Protocol 仍描述 on_event 回调；I-SESSION-5 派生主路径已是
# Session 快照 / SpineReader + fold。callback deriver 全部删除后再删本 Protocol。

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
