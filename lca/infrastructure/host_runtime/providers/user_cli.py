"""Host-runtime provider for LCA CLI deployment and per-user connect daemon control.

RA-014: the connect daemon has exactly one lifecycle owner — the lca-ops
``DaemonService``. ``CLIProvider`` keeps only CLI artifact deployment
(provision/status/heal); ``start_daemon``/``stop_daemon`` delegate to the
daemon-lifecycle seam instead of re-implementing spawn/pkill/pid-file logic.
"""


from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from lca.infrastructure.cli.config.config import DaemonConfig
from lca.infrastructure.cli.config.config import KernelServeConfig as CliKernelServeConfig
from lca.infrastructure.cli.service.service import http_ready, pid_alive
from lca.infrastructure.cli.services.daemon.daemon import DaemonService
from lca.infrastructure.cli.sudo.sudo import Sudo
from lca.infrastructure.host_runtime.config import HostRuntimeConfig, UserConfig
from lca.infrastructure.host_runtime.providers import CheckResult, Provider, StatusReport


def _daemon_service_for(config: HostRuntimeConfig, user: UserConfig) -> DaemonService:
    """Build the lca-ops DaemonService for a host-runtime user scope (RA-014).

    Maps host_runtime config shapes onto the single canonical daemon-lifecycle
    owner so ``CLIProvider.start/stop_daemon`` delegate instead of
    re-implementing the lifecycle. The drift-detection state dir is the
    cwd-relative ``.lca-ops`` operator dir — the same one the lca-ops path
    uses, so both operators share one CLI drift baseline. sudo reuses the
    password file the host runtime already reads (``.lobehub-stack/sudo.pass``);
    the cwd contract is the same one ``Provider.run_sudo`` already relies on.
    """
    health = urlsplit(config.kernel_serve.health_url)
    kernel_serve = CliKernelServeConfig(
        host=health.hostname or "127.0.0.1",
        port=health.port or 8765,
        health_path=health.path or "/health",
    )
    daemon_config = DaemonConfig(
        user=user.name,
        cli_dir=config.paths.cli_dir,
        token=config.kernel_serve.token,
        kernel_serve_ws_url=config.kernel_serve.url,
    )
    return DaemonService(
        config=daemon_config,
        kernel_serve=kernel_serve,
        state_dir=Path(".lca-ops"),
        root=Path.cwd(),
        sudo=Sudo(Path(".lobehub-stack/sudo.pass")),
    )


class CLIProvider(Provider):
    """Build and deploy the CLI; delegate connect-daemon lifecycle to DaemonService."""

    def __init__(
        self,
        config: HostRuntimeConfig,
        user: UserConfig | None = None,
        daemon: DaemonService | None = None,
    ) -> None:
        super().__init__(config)
        self.user = user
        # Injected daemon-lifecycle seam (composition, RA-014). Built lazily
        # from host_runtime config when None so existing call sites
        # (HostEnvironment) are untouched; tests inject a fake.
        self._daemon = daemon

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
                    ["npx", "tsc"],  # noqa: S607 -- npx via PATH is intentional in deploy provisioning
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
        """Start the detached CLI connect daemon for the configured user.

        Delegated to the DaemonService lifecycle seam (RA-014): the RA-006
        single-instance invariant and gateway-health gating apply here too.
        """
        if self.user is None:
            return False
        return self._daemon_service().start().is_running

    def stop_daemon(self) -> bool:
        """Stop the user's connect daemon and remove its pid file (delegated)."""
        if self.user is None:
            return True
        self._daemon_service().stop()
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
        """Restart the user daemon when its health check is the failed condition."""
        if failed_check.name == "daemon" and self.user:
            self.stop_daemon()
            return self.start_daemon()
        return False

    def _daemon_service(self) -> DaemonService:
        """Resolve the daemon-lifecycle seam: injected first, lazily built otherwise."""
        if self._daemon is not None:
            return self._daemon
        if self.user is None:
            raise AssertionError("user is None in _daemon_service")
        return _daemon_service_for(self.config, self.user)

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

    def _report_daemon_status(self, report: StatusReport) -> None:
        if self.user is None:
            raise AssertionError("user is None in _report_daemon_status")
        pid_file = Path(self.user.state_dir) / "connect.pid"
        if not pid_file.is_file():
            report.fail("daemon", "not running")
            return
        pid = int(pid_file.read_text().strip() or "0")
        if pid and pid_alive(pid):
            report.ok("daemon", f"pid={pid}")
        else:
            report.fail("daemon", "stale pid file")

    def _report_kernel_serve_status(self, report: StatusReport) -> None:
        """Probe kernel_serve reachability via the shared ``http_ready`` seam (RA-014).

        Converges on the same reachability probe DaemonService uses; the
        bespoke ``curl -sf`` subprocess probe (which also parsed the health
        body for a devices count) is gone.
        """
        if http_ready(self.config.kernel_serve.health_url, timeout=5.0):
            report.ok("kernel_serve", "reachable")
        else:
            report.warn("kernel_serve", "unreachable")


__all__ = ["CLIProvider"]
