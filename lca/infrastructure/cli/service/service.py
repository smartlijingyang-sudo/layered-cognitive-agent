"""Service Protocol — the core abstraction.

Every managed component (lobehub, infra, daemon; ADR-0119 followup-2: kernel_serve 已下线) implements
this interface. The CLI never talks to processes directly — it always
goes through a Service.

Four concerns, clearly separated:
    Lifecycle    — start / stop / restart  (process management)
    Setup        — ensure_ready            (idempotent preparation)
    Health       — state / heal            (observe and self-repair)
    Capabilities — cli_fingerprint_current / spawner
                   (optional; default = absent, callers fall through)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from lca.infrastructure.cli.services.kernel.spawner import KernelServeSpawner


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

    # ── Capabilities (optional; default = absent) ────────────────────

    def cli_fingerprint_current(self) -> bool:
        """True iff this service ships a managed CLI whose deployed copy
        matches the source fingerprint.

        Default False: services without a managed CLI never report current,
        so callers fall through to ``ensure_ready()``. Currently only
        ``DaemonService`` overrides this (the sandbox-user daemon CLI).
        """
        return False

    def spawner(self) -> KernelServeSpawner | None:
        """Return the process spawner for services that own their process
        lifecycle.

        Default None: callers fail-loud instead of hitting AttributeError.
        Currently only ``KernelServeService`` overrides this (ADR-0213 PR-3:
        ``stack.heal`` drives ``spawner().run()`` directly).
        """
        return None
