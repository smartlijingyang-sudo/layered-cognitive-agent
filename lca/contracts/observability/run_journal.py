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

    ADR-0164 Phase 6: 增 ``step_tree_writer`` 字段(可空), boot 把
    StepGroupedBackend + StepNarrativeWriter 装进来, 让 terminalizer
    在 close 时写 journal.json + narrative.md。 旧 writer 仍写 journal.raw.jsonl。
    """

    writer: JournalProjector
    tail: LiveRunProjection
    step_tree_writer: object | None = None  # StepGroupedBackend 实例(none 表示未启 step-tree)


@runtime_checkable
class RunJournalFactory(Protocol):
    """Profile-selected factory for runtime journal projections.

    ``RunLocator`` remains the sole owner of physical path derivation.  The
    factory receives the resolved durable path and selects the writer, live
    tail and process-wide projection implementation without involving Gateway.

    ``create_run_components`` 的 ``lifecycle_store`` 形参是可空注入:
    transport 在 run 启动期用 ``lca.runtime.journal_setup.build_step_lifecycle_store``
    构造好 store,显式注入到 factory。 factory 把它绑到 step-tree backend
    (让 ``journal.json`` 真的被写)。 不传时回退到 ContextVar 路径
    (供单元测试和 offline 脚本使用;生产路径必须传)。
    """

    def create_run_components(
        self,
        *,
        jsonl_path: Path,
        lifecycle_store: object | None = None,
    ) -> RunJournalComponents:
        """Create the durable writer and live tail for one run.

        参数:
            jsonl_path:    durable journal 路径(由 RunLocator 决定)
            lifecycle_store: 已 bind_run 的 StepLifecycleStore; 传 None
                           时回退到 ContextVar (legacy 单元测试用)
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
