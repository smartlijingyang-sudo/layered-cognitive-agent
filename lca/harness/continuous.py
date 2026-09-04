"""Durable, plugin-ready continuous control-plane service.

The control plane decides when an already constrained Session should be
activated. SQLite persistence and payload conversion are separate modules so
queue backends can be replaced without changing the scheduling boundary.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from lca.contracts.harness.tasks.continuous import (
    ContinuousControlPlane,
    ContinuousControlPlaneFactory,
    SessionWorkActivator,
    WorkItem,
    WorkLease,
    WorkQueue,
    WorkStatus,
)
from lca.harness.continuous_queue import LeaseNotOwnedError, SqliteWorkQueue
from lca.harness.continuous_serialization import require_aware


@dataclass(frozen=True, slots=True)
class SqliteContinuousControlPlaneFactory(ContinuousControlPlaneFactory):
    """Create a profile-owned SQLite control plane with explicit worker limits."""

    database_path: Path
    lease_seconds: int = 60
    retry_delay_seconds: float = 5.0

    def __post_init__(self) -> None:
        if self.lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        if self.retry_delay_seconds < 0:
            raise ValueError("retry_delay_seconds must be non-negative")

    def create(self) -> ContinuousControlPlane:
        """Return an isolated service sharing the configured durable queue."""

        return SqliteContinuousControlPlane(
            queue=SqliteWorkQueue(self.database_path),
            lease_seconds=self.lease_seconds,
            retry_delay_seconds=self.retry_delay_seconds,
        )


@dataclass(slots=True)
class SqliteContinuousControlPlane(ContinuousControlPlane):
    """Dispatch one leased activation through an injected Session bridge."""

    queue: WorkQueue
    lease_seconds: int = 60
    retry_delay_seconds: float = 5.0
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)

    def __post_init__(self) -> None:
        if self.lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        if self.retry_delay_seconds < 0:
            raise ValueError("retry_delay_seconds must be non-negative")

    def submit(self, item: WorkItem) -> WorkItem:
        """Record an external trigger as a durable, deduplicated work request."""

        return self.queue.submit(item)

    def get(self, work_id: str) -> WorkItem | None:
        """Read-only probe for one submitted work item (None when absent)."""

        return self.queue.get(work_id)

    def status_of(self, work_id: str) -> WorkStatus | None:
        """Read-only probe for one work item's durable status (None when absent)."""

        return self.queue.status_of(work_id)

    async def run_once(self, worker_id: str, activator: SessionWorkActivator) -> WorkLease | None:
        """Claim and dispatch one item without embedding loop or Session details."""

        lease = self.queue.claim(
            worker_id,
            now=require_aware(self.clock()),
            lease_seconds=self.lease_seconds,
        )
        if lease is None:
            return None
        item = self.queue.get(lease.work_id)
        if item is None:
            raise RuntimeError(f"claimed work item {lease.work_id!r} disappeared")
        try:
            receipt = await activator.activate(item)
        except asyncio.CancelledError:
            self._release(lease, delay=0, detail="worker_canceled")
            raise
        except Exception as error:
            self._release(
                lease,
                delay=self.retry_delay_seconds,
                detail=f"activation_error:{type(error).__name__}",
            )
        else:
            if receipt.accepted:
                self.queue.acknowledge(lease, receipt)
            else:
                self._release(
                    lease,
                    delay=self.retry_delay_seconds,
                    detail=receipt.detail or "activation_rejected",
                )
        return lease

    def _release(self, lease: WorkLease, *, delay: float, detail: str) -> None:
        self.queue.release(
            lease,
            now=require_aware(self.clock()),
            retry_delay_seconds=delay,
            detail=detail,
        )


__all__ = [
    "LeaseNotOwnedError",
    "SqliteContinuousControlPlane",
    "SqliteContinuousControlPlaneFactory",
    "SqliteWorkQueue",
]
