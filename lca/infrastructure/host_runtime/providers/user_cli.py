"""Host-runtime provider for LCA CLI deployment and per-user connect daemon control."""

# ruff: noqa: S101, S603, S607

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

from lca.infrastructure.host_runtime.config import HostRuntimeConfig, UserConfig
from lca.infrastructure.host_runtime.providers import CheckResult, Provider, StatusReport


class CLIProvider(Provider):
    """Build and deploy the CLI, then manage its optional per-user connect daemon."""

    def __init__(self, config: HostRuntimeConfig, user: UserConfig | None = None) -> None:
        super().__init__(config)
        self.user = user

    @property
    def name(self) -> str:
        """Return a stable global or user-scoped provider identity."""
        suffix = f":{self.user.name}" if self.user else ""
        return f"cli{suffix}"

    @property
    def _cli_js(self) -> Path:
        return Path(self.config.paths.cli_dir) / "dist" / "index.js"

    def provision(self) -> bool:
        """Build available CLI sources and deploy their runtime artifacts."""
        root = Path(".")
        source = root / self.config.cli.source_dir
        kernel_serve_client = root / self.config.cli.kernel_serve_client_dir
        destination = Path(self.config.paths.cli_dir)
        if (source / "src").is_dir():
            self.run(["npx", "tsc"], check=False)
            if (kernel_serve_client / "src").is_dir():
                subprocess.run(
                    ["npx", "tsc"],
                    cwd=str(kernel_serve_client),
                    capture_output=True,
                    timeout=60,
                )
        if not (source / "dist" / "index.js").is_file():
            return False
        self.run_sudo(["rm", "-rf", str(destination / "dist")])
        self.run_sudo(["cp", "-r", str(source / "dist"), str(destination)])
        if (kernel_serve_client / "dist").is_dir():
            client_destination = destination / "node_modules" / "@lca" / "gateway-client"
            self.run_sudo(["mkdir", "-p", str(client_destination)])
            self.run_sudo(["cp", "-r", str(kernel_serve_client / "dist"), str(client_destination)])
        for module_directory in [source / "node_modules", kernel_serve_client / "node_modules"]:
            if module_directory.is_dir():
                self.run_sudo(
                    ["cp", "-r", str(module_directory / "*"), str(destination / "node_modules")]
                )
        self.run_sudo(["chmod", "-R", "a+rX", str(destination)])
        self._ensure_wrapper()
        return True

    def start_daemon(self) -> bool:
        """Start the detached CLI connect daemon for the configured user."""
        if not self.user or not self._cli_js.is_file():
            return False
        pid_file = Path(self.user.state_dir) / "connect.pid"
        if pid_file.is_file():
            pid = int(pid_file.read_text().strip() or "0")
            if pid and self._pid_alive(pid):
                return True
        start_script = Path(self.user.state_dir) / "start.sh"
        self._write_start_script(start_script)
        log_file = Path(self.user.state_dir) / "daemon.log"
        self.run_sudo(["touch", str(log_file)])
        self.run_sudo(["chown", f"{self.user.name}:{self.user.name}", str(log_file)])
        self._launch_daemon(start_script)
        time.sleep(3)
        result = self.run(["pgrep", "-u", self.user.name, "-f", "node.*index.js.*connect"])
        if result.returncode != 0 or not result.stdout.strip():
            return False
        pid = int(result.stdout.strip().split("\n")[-1])
        self.run_sudo(["bash", "-c", f"echo '{pid}' > {pid_file}"])
        self.run_sudo(["chown", f"{self.user.name}:{self.user.name}", str(pid_file)])
        return True

    def stop_daemon(self) -> bool:
        """Stop the user's connect daemon and remove its pid file."""
        if not self.user:
            return True
        self.run(["pkill", "-u", self.user.name, "-f", "node.*index.js.*connect"])
        pid_file = Path(self.user.state_dir) / "connect.pid"
        if pid_file.is_file():
            self.run_sudo(["rm", "-f", str(pid_file)])
        return True

    def status(self) -> StatusReport:
        """Report deployment, daemon liveness, and kernel_serve connectivity when user-scoped."""
        report = StatusReport(self.name)
        if self._cli_js.is_file():
            report.ok("deployed", str(self.config.paths.cli_dir))
        else:
            report.fail("deployed", "CLI not found")
        if self.user:
            self._report_daemon_status(report)
            self._report_kernel_serve_status(report)
        return report

    def heal(self, failed_check: CheckResult) -> bool:
        """Restart a user daemon when its health check is the failed condition."""
        if failed_check.name == "daemon" and self.user:
            self.stop_daemon()
            return self.start_daemon()
        return False

    def _ensure_wrapper(self) -> None:
        wrapper_destination = Path(self.config.paths.tool_dir) / "lca"
        if wrapper_destination.is_file():
            return
        wrapper = f'#!/usr/bin/env bash\nexec node "{self._cli_js}" "$@"\n'
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as file:
            file.write(wrapper)
            file.flush()
            self.run_sudo(["cp", file.name, str(wrapper_destination)])
            self.run_sudo(["chmod", "+x", str(wrapper_destination)])
            Path(file.name).unlink(missing_ok=True)

    def _write_start_script(self, start_script: Path) -> None:
        assert self.user is not None
        script_content = f"""\
#!/bin/sh
export PATH="{self.config.paths.venv_dir}/bin:{self.config.paths.managed_path}"
export VIRTUAL_ENV={self.config.paths.venv_dir}
export HOME={self.user.home}
cd {self.user.home}
exec node {self._cli_js} connect \\
  --gateway {self.config.kernel_serve.url} \\
  --workspace {self.user.home} \\
  --token-type serviceToken \\
  --token {self.config.kernel_serve.token} \\
  >> "${{HOME}}/.lca/daemon.log" 2>&1
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as file:
            file.write(script_content)
            file.flush()
            self.run_sudo(["cp", file.name, str(start_script)])
            Path(file.name).unlink(missing_ok=True)
        self.run_sudo(["chown", f"{self.user.name}:{self.user.name}", str(start_script)])
        self.run_sudo(["chmod", "755", str(start_script)])

    def _launch_daemon(self, start_script: Path) -> None:
        assert self.user is not None
        password_file = Path(".lobehub-stack/sudo.pass")
        password = password_file.read_text().strip() if password_file.is_file() else ""
        subprocess.run(
            [
                "sudo",
                "-S",
                "-p",
                "",
                "-u",
                self.user.name,
                "setsid",
                "bash",
                "-c",
                f"nohup {start_script} </dev/null >/dev/null 2>&1 &",
            ],
            input=password,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=10,
        )

    def _report_daemon_status(self, report: StatusReport) -> None:
        assert self.user is not None
        pid_file = Path(self.user.state_dir) / "connect.pid"
        if not pid_file.is_file():
            report.fail("daemon", "not running")
            return
        pid = int(pid_file.read_text().strip() or "0")
        if pid and self._pid_alive(pid):
            report.ok("daemon", f"pid={pid}")
        else:
            report.fail("daemon", "stale pid file")

    def _report_kernel_serve_status(self, report: StatusReport) -> None:
        try:
            result = subprocess.run(
                ["curl", "-sf", self.config.kernel_serve.health_url],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                report.warn("kernel_serve", "unreachable")
                return
            data = json.loads(result.stdout)
            online = data.get("devices", {}).get("online", 0)
            report.ok("kernel_serve", f"online={online}")
        except Exception:
            report.warn("kernel_serve", "unreachable")

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True


__all__ = ["CLIProvider"]
