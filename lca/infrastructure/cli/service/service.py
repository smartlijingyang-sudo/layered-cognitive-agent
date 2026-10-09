"""Service Protocol — the core abstraction.

Every managed component (lobehub, infra, daemon; ADR-0119 followup-2: kernel_serve 已下线) implements
this interface. The CLI never talks to processes directly — it always
goes through a Service.

Three concerns, clearly separated:
    Lifecycle  — start / stop / restart  (process management)
    Setup      — ensure_ready            (idempotent preparation)
    Health     — state / heal            (observe and self-repair)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable


class ServiceStatus(Enum):
    """Service health state."""

    RUNNING = "running"
    STOPPED = "stopped"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class HealthCheck:
    """One health observation."""

    name: str
    ok: bool
    detail: str = ""


@dataclass(frozen=True, slots=True)
class ServiceState:
    """Snapshot of a service's current state.

    Returned by every lifecycle/health method so callers always
    know exactly what happened.
    """

    status: ServiceStatus
    checks: tuple[HealthCheck, ...] = ()
    pid: int | None = None
    port: int | None = None
    detail: str = ""
    why: str = ""
    next_action: str = ""

    @property
    def is_running(self) -> bool:
        return self.status == ServiceStatus.RUNNING

    @property
    def is_healthy(self) -> bool:
        return self.status in {ServiceStatus.RUNNING, ServiceStatus.DEGRADED}

    @property
    def needs_attention(self) -> bool:
        """True when the operator should do something."""
        return self.status != ServiceStatus.RUNNING or bool(self.next_action)


@runtime_checkable
class Service(Protocol):
    """A manageable platform component.

    All methods are idempotent — safe to call repeatedly.
    All lifecycle/health methods return ServiceState.
    """

    name: str

    # ── Lifecycle ──────────────────────────────────────────────────────

    def start(self) -> ServiceState:
        """Start the service. No-op if already running."""
        ...

    def stop(self) -> ServiceState:
        """Stop the service. No-op if already stopped."""
        ...

    def restart(self) -> ServiceState:
        """Restart the service. Default: stop + start."""
        ...

    # ── Setup (idempotent) ─────────────────────────────────────────────

    def ensure_ready(self) -> bool:
        """Ensure all prerequisites are met (sync, patches, deps, env).

        Returns True if any work was done, False if already ready.
        """
        ...

    # ── Health ─────────────────────────────────────────────────────────

    def state(self) -> ServiceState:
        """Observe current state without changing anything."""
        ...

    def heal(self) -> ServiceState:
        """Detect problems and attempt self-repair.

        Returns the state after healing attempt.
        """
        ...


@runtime_checkable
class CliShippingService(Protocol):
    """Services that ship a managed CLI binary on disk.

    Currently only ``DaemonService`` satisfies this; the CLI is the
    sandbox-user daemon. Other services (``LobehubService``, ``InfraService``,
    ``InfraService`` etc.) do not own a CLI and must not be type-checked
    against this Protocol.
    """

    def _cli_deployed(self) -> bool:
        """True iff the managed CLI binary is on disk and matches the
        expected fingerprint."""
        ...

    def _cli_source_changed(self) -> bool:
        """True iff the CLI source has changed since the last deploy."""
        ...
