"""One-shot kernel spawner — ``Popen`` + readiness probe.

Why a separate module
---------------------
``KernelSupervisor`` owns the long-lived lifecycle (autorestart,
backoff, event stream). ``KernelServeSpawner`` is the **single-shot**
spawn used by ``kernel check --boot`` and tests that need a synthetic
``Popen`` without supervisor threads.

Public surface
--------------
:class:`SpawnResult` carries only the minimum fields an operator /
agent needs to recover from a failed start:

- ``ok``        — did ``/health`` reach ``status=ok`` before timeout?
- ``pid``       — kernel PID (``None`` on spawn failure)
- ``port``      — configured HTTP port
- ``exit_code`` — kernel exit code (``None`` if still alive at handoff)
- ``duration_ms`` — total wall-clock time

Stderr / stdout go to the supervisor's logfiles; we do **not** parse
or grep them. Diagnostic hints live in :class:`PlanLiftError`'s
``next_command`` field and ``lca-ops kernel check``.
"""

from __future__ import annotations

import subprocess
import sys
import time

from pydantic import BaseModel, ConfigDict

from lca.infrastructure.cli.config.config import KernelServeConfig
from lca.infrastructure.cli.service.service import health_body_ok

_HEALTH_TIMEOUT_S = 30.0
_HEALTH_POLL_S = 0.5


class SpawnResult(BaseModel):
    """One-shot spawn outcome.

    Wire-stable; ``model_config`` is frozen + extra-forbid so consumers
    can rely on the shape.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: bool
    pid: int | None = None
    port: int
    exit_code: int | None = None
    duration_ms: int = 0


class KernelServeSpawner:
    """Spawn ``lca_kernel serve`` once; observe /health until ready."""

    def __init__(
        self,
        config: KernelServeConfig,
        root,
        *,
        health_timeout: float = _HEALTH_TIMEOUT_S,
    ) -> None:
        self._config = config
        self._root = root
        self._health_timeout = health_timeout

    @property
    def health_url(self) -> str:
        probe_host = "127.0.0.1" if self._config.host in ("0.0.0.0", "::") else self._config.host  # noqa: S104 — bind-all sentinel
        return f"http://{probe_host}:{self._config.port}/health"

    def run(self) -> SpawnResult:
        """Spawn, probe /health, return result."""
        start_ts = time.monotonic()
        port = self._config.port
        profile = self._config.profile

        try:
            proc = subprocess.Popen(  # noqa: S603 — argv list, no shell
                [
                    sys.executable, "-m", "lca_kernel", "serve",
                    "--profile", profile,
                    "--host", self._config.host,
                    "--port", str(port),
                    "--allow-unknown-env",
                ],
                cwd=str(self._root),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                close_fds=True,
            )
        except OSError:
            return SpawnResult(
                ok=False, port=port,
                duration_ms=int((time.monotonic() - start_ts) * 1000),
            )

        deadline = time.monotonic() + self._health_timeout
        while time.monotonic() < deadline:
            rc = proc.poll()
            if rc is not None:
                return SpawnResult(
                    ok=False, pid=proc.pid, port=port, exit_code=rc,
                    duration_ms=int((time.monotonic() - start_ts) * 1000),
                )
            if health_body_ok(self.health_url, timeout=1.0):
                return SpawnResult(
                    ok=True, pid=proc.pid, port=port,
                    duration_ms=int((time.monotonic() - start_ts) * 1000),
                )
            time.sleep(_HEALTH_POLL_S)

        # Timed out; subprocess still running. Return failure with
        # caller's choice to kill.
        return SpawnResult(
            ok=False, pid=proc.pid, port=port,
            duration_ms=int((time.monotonic() - start_ts) * 1000),
        )


__all__ = ["KernelServeSpawner", "SpawnResult"]
