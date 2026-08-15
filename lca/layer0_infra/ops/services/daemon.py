"""Daemon service — sandbox-user CLI connect daemon.

Manages the TypeScript CLI daemon that connects sandbox-user to the gateway.
Lifecycle: start/stop the node process.
Health: check PID file and process.
Setup: ensure CLI is deployed to /opt/lca.

Source drift detection: ``StateStore.detect_changes`` compares CLI source tree
against the last snapshot. ``status`` shows exactly which files changed.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from lca.layer0_infra.ops.config import DaemonConfig, GatewayConfig
from lca.layer0_infra.ops.service import (
    HealthCheck,
    ServiceState,
    ServiceStatus,
    pid_alive,
)
from lca.layer0_infra.ops.state import StateStore
from lca.layer0_infra.ops.sudo import Sudo


class DaemonService:
    """Sandbox-user CLI daemon.

    Manages the node process that connects sandbox-user to the gateway
    via WebSocket, receiving and executing tool calls.
    """

    def __init__(
        self,
        config: DaemonConfig,
        gateway: GatewayConfig,
        state_dir: Path,
        root: Path,
        sudo: Sudo,
    ) -> None:
        self.name = "daemon"
        self._config = config
        self._gateway = gateway
        self._state = StateStore(state_dir)
        self._root = root
        self._sudo = sudo
        self._cli_dir = Path("/opt/lca")
        self._user_state = Path(f"/home/{self._config.user}/.lca")

    @property
    def _gateway_ws_url(self) -> str:
        """Resolve gateway WebSocket URL from config."""
        if self._config.gateway_ws_url:
            return self._config.gateway_ws_url
        return f"ws://{self._gateway.host}:{self._gateway.port}"

    @property
    def _gateway_health_url(self) -> str:
        """Resolve gateway health check URL."""
        return f"{self._gateway.base_url}{self._gateway.health_path}"

    # ── Lifecycle ─────────────────────────────────────────────────────

    def start(self) -> ServiceState:
        """Start the daemon if not already running. Auto-redeploys CLI if source changed."""
        current = self.state()
        if current.is_running:
            return current

        # Ensure CLI is deployed and up-to-date
        self.ensure_ready()
        if not self._cli_deployed():
            return ServiceState(
                status=ServiceStatus.STOPPED,
                detail="CLI not deployed to /opt/lca",
            )

        pid = self._spawn()
        if pid is None:
            return ServiceState(status=ServiceStatus.STOPPED, detail="spawn failed")

        time.sleep(1)
        if pid_alive(pid):
            self._write_user_pid(pid)
            return ServiceState(
                status=ServiceStatus.RUNNING,
                pid=pid,
                detail=f"connected to {self._gateway_ws_url}",
            )

        return ServiceState(status=ServiceStatus.STOPPED, detail="process died")

    def stop(self) -> ServiceState:
        """Stop the daemon."""
        # Kill by user process match
        try:
            subprocess.run(
                ["pkill", "-u", self._config.user, "-f", "node.*index.js.*connect"],
                capture_output=True,
                timeout=5,
            )
        except Exception:
            pass

        self._sudo.rm(self._user_state / "connect.pid")

        return ServiceState(status=ServiceStatus.STOPPED)

    def restart(self) -> ServiceState:
        """Restart the daemon."""
        self.stop()
        time.sleep(0.5)
        return self.start()

    # ── Setup ─────────────────────────────────────────────────────────

    @property
    def _cli_src_paths(self) -> list[Path]:
        src = self._root / "packages" / "lca-cli"
        return [src / "src", src / "package.json", src / "tsconfig.json"]

    def ensure_ready(self) -> bool:
        """Ensure CLI is deployed and up-to-date with source.

        Returns True if (re)deploy happened, False if already current.
        Uses ``StateStore.detect_changes`` for file-level drift detection.
        """
        report = self._state.detect_changes("daemon_cli", self._cli_src_paths, "*.ts")
        if self._cli_deployed() and not report.has_changes:
            return False
        return self._deploy_cli()

    def _cli_source_changed(self) -> bool:
        """True when CLI source differs from last deployed snapshot."""
        return self._state.detect_changes("daemon_cli", self._cli_src_paths, "*.ts").has_changes

    def _cli_change_report(self):
        """Rich change report for status display."""
        return self._state.detect_changes("daemon_cli", self._cli_src_paths, "*.ts")

    # ── Health ────────────────────────────────────────────────────────

    def state(self) -> ServiceState:
        """Observe current state — includes source drift with file details."""
        checks: list[HealthCheck] = []

        # CLI deployed?
        cli_ok = self._cli_deployed()
        checks.append(HealthCheck("cli", cli_ok, str(self._cli_dir)))

        # Source drift via unified ChangeReport
        report = self._cli_change_report()
        checks.append(HealthCheck("cli_sync", not report.has_changes, report.summary))

        # Daemon running?
        pid = self._read_user_pid()
        process_ok = pid is not None and pid_alive(pid)
        checks.append(HealthCheck("daemon", process_ok, f"pid={pid}" if pid else "not running"))

        # Gateway reachable?
        try:
            result = subprocess.run(
                ["curl", "-sf", "--max-time", "2", self._gateway_health_url],
                capture_output=True,
                timeout=5,
            )
            gw_ok = result.returncode == 0
            checks.append(HealthCheck("gateway", gw_ok, "reachable" if gw_ok else "unreachable"))
        except Exception:
            checks.append(HealthCheck("gateway", False, "unreachable"))
            gw_ok = False

        if cli_ok and process_ok:
            status = ServiceStatus.RUNNING
            if report.has_changes:
                detail = f"running (CLI stale — {report.summary})"
                why = "CLI source changed since last deploy; daemon runs old code"
                next_action = "./scripts/lca-ops daemon restart"
            else:
                detail = "connected"
                why = ""
                next_action = ""
        elif not cli_ok:
            status = ServiceStatus.STOPPED
            detail = "CLI not deployed"
            why = f"{self._cli_dir}/dist/index.js is missing"
            next_action = "./scripts/lca-ops daemon ensure"
        else:
            status = ServiceStatus.STOPPED
            detail = "daemon not running"
            why = f"{self._config.user} is not connected — agent tools on this host will fail"
            next_action = "./scripts/lca-ops daemon start"

        return ServiceState(
            status=status,
            checks=tuple(checks),
            pid=pid if process_ok else None,
            detail=detail,
            why=why,
            next_action=next_action,
        )

    def heal(self) -> ServiceState:
        """Auto-recover: deploy CLI if needed, restart if stale or down."""
        current = self.state()
        # Running and no stale code → nothing to do
        if current.is_running and not current.next_action:
            return current
        # Source changed or daemon down → full ensure + restart
        self.ensure_ready()
        return self.restart()

    # ── Internals ─────────────────────────────────────────────────────

    def _cli_deployed(self) -> bool:
        """Check if CLI is deployed."""
        cli_js = self._cli_dir / "dist" / "index.js"
        return cli_js.exists()

    def _deploy_cli(self) -> bool:
        """Deploy CLI from source to /opt/lca. Writes fingerprint marker."""
        src = self._root / "packages" / "lca-cli"
        if not (src / "src").is_dir():
            return False

        # Build TypeScript
        try:
            subprocess.run(
                ["npx", "tsc"],
                cwd=src,
                capture_output=True,
                timeout=60,
            )
        except Exception:
            return False

        if not (src / "dist" / "index.js").exists():
            return False

        self._sudo.run(["rm", "-rf", str(self._cli_dir / "dist")])
        copied = self._sudo.run(["cp", "-r", str(src / "dist"), str(self._cli_dir)])
        if copied.returncode != 0:
            return False
        if (src / "node_modules").exists():
            self._sudo.run(["cp", "-r", str(src / "node_modules"), str(self._cli_dir)])
        self._sudo.run(["chmod", "-R", "a+rX", str(self._cli_dir)])

        # Save snapshot so future detect_changes has a baseline.
        self._state.save_snapshot("daemon_cli", self._cli_src_paths, "*.ts")
        return True

    def _spawn(self) -> int | None:
        """Spawn the daemon process as sandbox-user."""
        cli_js = self._cli_dir / "dist" / "index.js"
        if not cli_js.exists():
            return None

        owner = self._config.user
        if not self._sudo.mkdir(self._user_state, owner=owner):
            return None

        start_script = self._user_state / "start.sh"
        script_content = f"""#!/bin/sh
export PATH="/opt/lca/venv/bin:/usr/local/bin:/usr/bin:/bin"
export HOME=/home/{owner}
cd {self._config.workspace}
exec node {cli_js} connect \\
  --gateway {self._gateway_ws_url} \\
  --workspace {self._config.workspace} \\
  --token-type serviceToken \\
  --token lca-local-host \\
  >> "${{HOME}}/.lca/daemon.log" 2>&1
"""
        if not self._sudo.write_text(start_script, script_content, owner=owner):
            return None
        self._sudo.run(["chmod", "755", str(start_script)])

        launched = self._sudo.run(
            ["setsid", "bash", "-c", f"nohup {start_script} </dev/null >/dev/null 2>&1 &"],
            user=owner,
            timeout=10,
        )
        if launched.returncode != 0:
            return None

        time.sleep(1)
        pid_result = subprocess.run(
            ["pgrep", "-u", owner, "-f", "node.*index.js.*connect"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if pid_result.returncode == 0 and pid_result.stdout.strip():
            return int(pid_result.stdout.strip().split("\n")[-1])
        return None

    def _read_user_pid(self) -> int | None:
        text = self._sudo.read_text(self._user_state / "connect.pid")
        if not text:
            return None
        try:
            return int(text.strip())
        except ValueError:
            return None

    def _write_user_pid(self, pid: int) -> None:
        self._sudo.write_text(
            self._user_state / "connect.pid",
            f"{pid}\n",
            owner=self._config.user,
        )
