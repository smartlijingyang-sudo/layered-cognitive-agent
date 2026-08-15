"""Service Protocol — the core abstraction.

Every managed component (gateway, lobehub, infra, daemon) implements
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


# ── Process management primitives ─────────────────────────────────────


def kill_tree(pid: int, sig: int = 15) -> None:
    """Kill a process and all its descendants."""
    import os

    if pid <= 0:
        return

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return

    # Kill children first (depth-first)
    try:
        import subprocess

        children = subprocess.run(
            ["pgrep", "-P", str(pid)],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for child_pid in children.stdout.strip().split("\n"):
            if child_pid.strip():
                kill_tree(int(child_pid.strip()), sig)
    except Exception:
        pass

    try:
        os.kill(pid, sig)
    except ProcessLookupError:
        pass


def free_port(port: int) -> None:
    """Release a port from any holder."""
    import subprocess

    try:
        subprocess.run(
            ["fuser", "-k", f"{port}/tcp"],
            capture_output=True,
            timeout=5,
        )
    except Exception:
        pass


def pid_alive(pid: int) -> bool:
    """Check if a PID is alive."""
    import os

    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def http_ready(url: str, timeout: float = 2.0) -> bool:
    """Check if an HTTP endpoint is reachable.

    Uses ``-sS`` (not ``-f``) so a 4xx/5xx still counts as "server is up".
    """
    import subprocess

    try:
        r = subprocess.run(
            ["curl", "-sS", "--max-time", str(timeout), "-o", "/dev/null", url],
            capture_output=True,
            timeout=timeout + 1,
        )
        return r.returncode == 0
    except Exception:
        return False
