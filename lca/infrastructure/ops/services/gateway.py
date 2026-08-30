"""Gateway service — LCA API gateway (Starlette/uvicorn).

Lifecycle: start uvicorn, stop process tree, restart.
Health: HTTP health check on /health endpoint.
Setup: no-op (gateway has no prerequisites beyond Python).
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from lca.infrastructure.ops.config import GatewayConfig
from lca.infrastructure.ops.service import (
    HealthCheck,
    ServiceState,
    ServiceStatus,
    free_port,
    http_ready,
    kill_tree,
    pid_alive,
)
from lca.infrastructure.ops.state import StateStore


class GatewayService:
    """LCA API gateway.

    Manages the uvicorn process serving gateway.app:app.
    """

    def __init__(self, config: GatewayConfig, state_dir: Path, root: Path) -> None:
        self.name = "gateway"
        self._config = config
        self._state = StateStore(state_dir)
        self._root = root

    # ── Lifecycle ─────────────────────────────────────────────────────

    def start(self) -> ServiceState:
        """Start the gateway if not already running."""
        current = self.state()
        if current.is_running:
            return current

        pid = self._spawn()
        if pid is None:
            return ServiceState(status=ServiceStatus.STOPPED, detail="spawn failed")

        # Wait for health
        for _ in range(40):
            time.sleep(0.25)
            if self._is_healthy():
                self._state.write_pid(self.name, pid)
                self._state.save_snapshot("gateway", [self._root / "gateway", self._root / "lca"])
                return ServiceState(
                    status=ServiceStatus.RUNNING,
                    pid=pid,
                    port=self._config.port,
                    detail="ready",
                )

        return ServiceState(
            status=ServiceStatus.STOPPED,
            pid=pid,
            detail="start timeout",
        )

    def stop(self) -> ServiceState:
        """Stop the gateway."""
        pid = self._state.read_pid(self.name)
        if pid and pid_alive(pid):
            kill_tree(pid)
            time.sleep(0.5)

        free_port(self._config.port)
        self._state.remove_pid(self.name)
        return ServiceState(status=ServiceStatus.STOPPED)

    def restart(self) -> ServiceState:
        """Restart the gateway."""
        self.stop()
        return self.start()

    # ── Setup ─────────────────────────────────────────────────────────

    def ensure_ready(self) -> bool:
        """Gateway has no prerequisites. Always ready."""
        return False

    # ── Health ────────────────────────────────────────────────────────

    def state(self) -> ServiceState:
        """Observe current state."""
        pid = self._state.read_pid(self.name)
        checks: list[HealthCheck] = []

        # Process alive?
        process_ok = pid is not None and pid_alive(pid)
        checks.append(HealthCheck("process", process_ok, f"pid={pid}" if pid else "none"))

        # Port listening?
        port_ok = http_ready(self._config.health_url)
        checks.append(HealthCheck("health", port_ok))

        # Code changed?
        report = self._state.detect_changes("gateway", [self._root / "gateway", self._root / "lca"])
        checks.append(HealthCheck("code_sync", not report.has_changes, report.summary))

        why = ""
        next_action = ""
        if process_ok and port_ok:
            status = ServiceStatus.RUNNING
            detail = "healthy"
            if report.has_changes:
                detail = f"healthy (code changed — {report.summary})"
                why = "Python source is newer than this process"
                next_action = "./scripts/lca-ops gateway restart"
        elif process_ok:
            status = ServiceStatus.DEGRADED
            detail = "process alive but health check failed"
            why = f"port {self._config.port} is not answering {self._config.health_path}"
            next_action = "./scripts/lca-ops gateway restart"
        else:
            status = ServiceStatus.STOPPED
            detail = "not running"
            why = "API /health is down — LobeHub and daemon cannot talk to LCA"
            next_action = "./scripts/lca-ops gateway start"

        return ServiceState(
            status=status,
            checks=tuple(checks),
            pid=pid if process_ok else None,
            port=self._config.port,
            detail=detail,
            why=why,
            next_action=next_action,
        )

    def heal(self) -> ServiceState:
        """Restart when down or when watched source is newer than this process."""
        current = self.state()
        if current.is_running and not current.next_action:
            return current
        return self.restart()

    # ── Internals ─────────────────────────────────────────────────────

    def _spawn(self) -> int | None:
        """Spawn the gateway process. Returns PID or None."""
        log_path = self._state.log_file(self.name)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            log_handle = log_path.open("a")
            proc = subprocess.Popen(
                [
                    *self._config.entry,
                    "--host",
                    self._config.bind,
                    "--port",
                    str(self._config.port),
                ],
                cwd=self._root,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            return proc.pid
        except Exception:
            return None

    def _is_healthy(self) -> bool:
        """Quick health check."""
        return http_ready(self._config.health_url, timeout=1.0)
