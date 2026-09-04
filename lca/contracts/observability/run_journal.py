"""Run journal assembly contracts.

A run has three deliberately separate observable views: a durable per-run writer,
a per-run live tail, and one process-wide live projection.  Gateway owns the
HTTP transport that consumes these views, but it must not choose or construct
their implementations.  A profile-selected factory closes that implementation
choice behind the contracts in this module.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from lca.contracts.models.observability.journal import StampedEvent
from lca.contracts.protocols.journal.journal import JournalProjector


@runtime_checkable
class LiveRunProjection(JournalProjector, Protocol):
    """A bounded, replayable live projection for one run.

    The yielded control objects are intentionally opaque to the contract.  The
    transport adapter that owns their wire representation interprets them,
    while a factory replacement only has to preserve ordered event delivery.
    """

    @property
    def buffer_size(self) -> int:
        """Number of currently replayable entries."""
        ...

    @property
    def subscriber_count(self) -> int:
        """Number of active live consumers."""
        ...

    @property
    def evicted(self) -> int:
        """Number of consumers removed after sustained overflow."""
        ...

    def subscribe(self, after_seq: int = 0) -> AsyncIterator[StampedEvent | object]:
        """Replay entries after ``after_seq`` and then yield live entries."""
        ...


@runtime_checkable
class ProcessJournalProjection(Protocol):
    """Long-lived process projection that can contribute to individual runs."""

    @property
    def tail(self) -> LiveRunProjection:
        """The process-wide live projection."""
        ...

    def bind(self) -> JournalProjector:
        """Create a run-scoped projector without transferring process ownership."""
        ...


@dataclass(frozen=True)
class RunJournalComponents:
    """Run-scoped writer and live tail created as one coherent unit.

    ADR-0167 D11 / ADR-0186 PR-3g: 移除 ``lifecycle_store`` 注入。journal.json 由
    ``StepTreeFoldDeriver`` 落盘(transport 在 prepare 时装配 fold deriver)。
    ``step_tree_writer`` 是 ``_StepTreeBundle`` 引用,由 RunSessionBuilder
    装配 deriver 后再填回。
    """

    writer: JournalProjector
    tail: LiveRunProjection
    step_tree_writer: object | None = None  # _StepTreeBundle 实例


@runtime_checkable
class RunJournalFactory(Protocol):
    """Profile-selected factory for runtime journal projections.

    ADR-0167 D11 简化: 移除 lifecycle_store 注入形参。 factory 只构造
    LiveTail + 空 step_tree_writer; deriver 由 transport 在 run 准备期
    装配到 bundle 上。
    """

    def create_run_components(
        self,
        *,
        spine_path: Path,
    ) -> RunJournalComponents:
        """Create the live tail for one run.

        参数:
            spine_path:    落盘 spine 事件流路径(``<run_id>.spine.jsonl``;由 RunLocator 决定)
        """
        ...

    def create_process_journal(self) -> ProcessJournalProjection:
        """Create the single long-lived projection for the current process."""
        ...


__all__ = [
    "LiveRunProjection",
    "ProcessJournalProjection",
    "RunJournalComponents",
    "RunJournalFactory",
]
