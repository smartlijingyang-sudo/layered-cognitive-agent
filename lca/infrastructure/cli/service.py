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

import contextlib
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
    sandbox-user daemon. Other services (``GatewayService``,
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

        children = subprocess.run(  # noqa: S603
            ["pgrep", "-P", str(pid)],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=5,
        )
        for child_pid in children.stdout.strip().split("\n"):
            if child_pid.strip():
                kill_tree(int(child_pid.strip()), sig)
    except Exception:  # noqa: S110
        pass

    with contextlib.suppress(ProcessLookupError):
        os.kill(pid, sig)


def free_port(port: int) -> None:
    """Release a port from any holder."""
    import subprocess

    with contextlib.suppress(Exception):
        subprocess.run(  # noqa: S603
            ["fuser", "-k", f"{port}/tcp"],  # noqa: S607
            capture_output=True,
            timeout=5,
        )


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


def pid_on_port(port: int) -> int | None:
    """Return a PID listening on ``port``, or None if none found.

    Prefer ``lsof`` / ``ss``. ``fuser`` is not used: it prints stray PIDs
    that are not bound to the port, which made the Vite sidecar look up.
    """
    import re
    import subprocess

    try:
        result = subprocess.run(  # noqa: S603
            ["lsof", "-ti", f"tcp:{port}"],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=5,
        )
        for line in result.stdout.strip().split("\n"):
            if line.strip():
                return int(line.strip())
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass

    try:
        result = subprocess.run(
            ["ss", "-tlnp"],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=5,
        )
        bound = re.compile(rf":{port}\s")
        for line in result.stdout.splitlines():
            if not bound.search(line):
                continue
            match = re.search(r"pid=(\d+)", line)
            if match:
                return int(match.group(1))
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    return None


def http_ready(url: str, timeout: float = 2.0) -> bool:
    """Check if an HTTP endpoint is reachable.

    Uses ``-sS`` (not ``-f``) so a 4xx/5xx still counts as "server is up".
    """
    import subprocess

    try:
        r = subprocess.run(  # noqa: S603
            ["curl", "-sS", "--max-time", str(timeout), "-o", "/dev/null", url],  # noqa: S607
            capture_output=True,
            timeout=timeout + 1,
        )
        return r.returncode == 0
    except Exception:
        return False
