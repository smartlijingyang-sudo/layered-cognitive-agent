"""VisitRecorder — collects :class:`VisitRecord` for observability and debug.

The recorder is the single seam the kernel writes to for trace data.
Observability backends subscribe to the recorder (and to the existing
journal seam) rather than the kernel itself. Tests assert against
the recorder's collected list to pin visit history.

The recorder does not own state mutation; it is pure observation.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from lca.contracts.protocols.graph.visit import VisitRecord


class VisitRecorder:
    """In-memory :class:`VisitRecord` collector."""

    def __init__(self) -> None:
        self._records: list[VisitRecord] = []

    def record(self, visit: VisitRecord) -> None:
        self._records.append(visit)

    def all(self) -> tuple[VisitRecord, ...]:
        return tuple(self._records)

    def last(self) -> VisitRecord | None:
        return self._records[-1] if self._records else None

    def clear(self) -> None:
        self._records.clear()

    def by_node(self, node_id: str) -> tuple[VisitRecord, ...]:
        return tuple(r for r in self._records if r.node_id == node_id)


__all__ = ["VisitRecorder"]