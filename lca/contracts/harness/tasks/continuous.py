"""Contracts for the durable continuous control plane.

The continuous control plane decides *when* a constrained Session should run.  It
is intentionally outside the six cognitive phases: once a work item is activated,
all reasoning, effect governance, approval, and state reduction remain owned by
the existing Session Spine and declarative runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable


class TriggerKind(StrEnum):
    """Trusted trigger categories accepted by the continuous control plane."""

    MANUAL = "manual"
    SCHEDULE = "schedule"
    EVENT = "event"
    RETRY = "retry"


class WorkStatus(StrEnum):
    """Durable lifecycle states for a scheduled activation request."""

    PENDING = "pending"
    LEASED = "leased"
    DISPATCHED = "dispatched"
    RETRY_WAIT = "retry_wait"
    DEAD = "dead"
    CANCELED = "canceled"


@dataclass(frozen=True, slots=True)
class Trigger:
    """An immutable fact that may request one constrained Session activation."""

    trigger_id: str
    kind: TriggerKind
    occurred_at: datetime
    subject: str
    payload: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str = ""

    def __post_init__(self) -> None:
        if not self.trigger_id.strip():
            raise ValueError("trigger_id must not be empty")
        if not self.subject.strip():
            raise ValueError("trigger subject must not be empty")
        if not self.idempotency_key.strip():
            object.__setattr__(self, "idempotency_key", self.trigger_id)


@dataclass(frozen=True, slots=True)
class WorkItem:
    """A bounded, auditable request to activate or continue one Session.

    ``session_id`` resumes an existing Session.  A new Session requires a
    profile so the Session Spine can resolve a fixed plugin plan before work is
    dispatched.  ``grant`` is carried as immutable provenance for a future
    policy/activator; this control-plane primitive never widens it.
    """

    work_id: str
    trigger: Trigger
    profile: str | None = None
    preset: str | None = None
    session_id: str | None = None
    message: str = ""
    options: dict[str, Any] = field(default_factory=dict)
    grant: tuple[str, ...] = ()
    max_attempts: int = 3
    available_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.work_id.strip():
            raise ValueError("work_id must not be empty")
        if self.session_id is None and not (self.profile or "").strip():
            raise ValueError("new work items require a profile")
        if self.max_attempts <= 0:
            raise ValueError("max_attempts must be positive")
        if not isinstance(self.grant, tuple):
            object.__setattr__(self, "grant", tuple(str(item) for item in self.grant))
        if self.available_at is not None and self.available_at.tzinfo is None:
            raise ValueError("available_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class WorkLease:
    """An exclusive, time-bounded ownership token for one queued work item."""

    work_id: str
    lease_id: str
    worker_id: str
    acquired_at: datetime
    expires_at: datetime
    attempt: int

    def __post_init__(self) -> None:
        if not self.work_id.strip() or not self.lease_id.strip() or not self.worker_id.strip():
            raise ValueError("work lease identifiers must not be empty")
        if self.acquired_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("work lease times must be timezone-aware")
        if self.expires_at <= self.acquired_at:
            raise ValueError("work lease expiry must follow acquisition")
        if self.attempt <= 0:
            raise ValueError("work lease attempt must be positive")


@dataclass(frozen=True, slots=True)
class WorkActivationReceipt:
    """The idempotent result of dispatching a work item to a Session."""

    accepted: bool
    session_id: str | None = None
    detail: str = ""


@runtime_checkable
class WorkQueue(Protocol):
    """Durable queue boundary.  Claims are exclusive and lease-verified."""

    def submit(self, item: WorkItem) -> WorkItem: ...

    def get(self, work_id: str) -> WorkItem | None: ...

    def status_of(self, work_id: str) -> WorkStatus | None: ...

    def claim(self, worker_id: str, *, now: datetime, lease_seconds: int) -> WorkLease | None: ...

    def acknowledge(self, lease: WorkLease, receipt: WorkActivationReceipt) -> None: ...

    def release(
        self,
        lease: WorkLease,
        *,
        now: datetime,
        retry_delay_seconds: float,
        detail: str,
    ) -> WorkStatus: ...

    def cancel(self, work_id: str) -> bool: ...


@runtime_checkable
class SessionWorkActivator(Protocol):
    """Bridge a claimed work item to the existing command-backed Session Spine."""

    async def activate(self, item: WorkItem) -> WorkActivationReceipt: ...


@runtime_checkable
class ContinuousControlPlane(Protocol):
    """Profile-selected service for trigger ingestion and leased dispatch.

    ``get`` / ``status_of`` are read-only probes into the durable queue so
    declarative producers (e.g. ``assistant.jobs``, ADR-0187 §3 D10) can
    verify a submitted work item without owning lease or dispatch.
    """

    def submit(self, item: WorkItem) -> WorkItem: ...

    def get(self, work_id: str) -> WorkItem | None: ...

    def status_of(self, work_id: str) -> WorkStatus | None: ...

    async def run_once(
        self, worker_id: str, activator: SessionWorkActivator
    ) -> WorkLease | None: ...


@runtime_checkable
class ContinuousControlPlaneFactory(Protocol):
    """Construct a profile-owned continuous control-plane service."""

    def create(self) -> ContinuousControlPlane: ...


__all__ = [
    "ContinuousControlPlane",
    "ContinuousControlPlaneFactory",
    "SessionWorkActivator",
    "Trigger",
    "TriggerKind",
    "WorkActivationReceipt",
    "WorkItem",
    "WorkLease",
    "WorkQueue",
    "WorkStatus",
]
