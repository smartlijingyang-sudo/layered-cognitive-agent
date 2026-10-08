"""Host-runtime provider for LCA CLI deployment and per-user connect daemon control.

RA-014: the connect daemon has exactly one lifecycle owner — the lca-ops
``DaemonService``. ``CLIProvider`` keeps only CLI artifact deployment
(provision/status/heal); ``start_daemon``/``stop_daemon`` delegate to the
daemon-lifecycle seam instead of re-implementing spawn/pkill/pid-file logic.

RA-028: the observation path delegates too — ``status()`` projects daemon
liveness and gateway reachability from ``DaemonService.state()`` (no second
pid-file path derivation, no second gateway probe), and ``heal()`` restarts
through ``DaemonService.restart()``.
"""


from __future__ import annotations

import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlsplit

from lca.infrastructure.cli.config.config import DaemonConfig
from lca.infrastructure.cli.config.config import KernelServeConfig as CliKernelServeConfig
from lca.infrastructure.cli.service.service import ServiceState
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


def _stage_privileged_file(
    run_sudo: Callable[[list[str]], object],
    content: str,
    dest: Path,
    *,
    owner: str | None = None,
    mode: str | None = None,
) -> None:
    """Stage a privileged file via tempfile + sudo cp, then apply owner/mode (RA-015).

    The tempfile -> sudo cp -> unlink -> chmod/chown ceremony lives exactly
    here -- the unlink discipline is a security surface (the staging tempfile
    never stays on disk). Future hardening (backup-before-write, post-write
    verify) is a one-place edit. ``run_sudo`` is injected (``Provider.run_sudo``
    in production) so tests can pin the call sequence with a fake.
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as file:
        file.write(content)
        file.flush()
        # unlink in finally: a failing sudo call must not leave the staging
        # tempfile (holding privileged content) on disk.
        try:
            run_sudo(["cp", file.name, str(dest)])
            if owner is not None:
                run_sudo(["chown", owner, str(dest)])
            if mode is not None:
                run_sudo(["chmod", mode, str(dest)])
        finally:
            Path(file.name).unlink(missing_ok=True)


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
        """Report deployment, daemon liveness, and kernel_serve connectivity when user-scoped.

        Daemon liveness and gateway reachability project from the injected
        DaemonService's ``state()`` (RA-028): "where the pid file is" and "is
        the gateway reachable" are computed exactly once, by the lifecycle
        owner. The CLI-deployed check stays in the provider — it is the
        provider's own deployment surface.
        """
        report = StatusReport(self.name)
        if self._cli_js.is_file():
            report.ok("deployed", str(self.config.paths.cli_dir))
        else:
            report.fail("deployed", "CLI not found")
        if self.user:
            state = self._daemon_service().state()
            self._project_check(report, state, source="daemon", target="daemon")
            self._project_check(
                report,
                state,
                source="gateway",
                target="kernel_serve",
                warn_when_unhealthy=True,
            )
        return report

    def heal(self, failed_check: CheckResult) -> bool:
        """Restart the user daemon when its health check is the failed condition.

        Delegates to the DaemonService ``restart()`` seam (RA-028): stop+start
        with the RA-006 single-instance invariant (old process confirmed dead
        before spawning) is owned there, not hand-rolled here.
        """
        if failed_check.name == "daemon" and self.user:
            return self._daemon_service().restart().is_running
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
        _stage_privileged_file(self.run_sudo, wrapper, wrapper_destination, mode="+x")

    @staticmethod
    def _project_check(
        report: StatusReport,
        state: ServiceState,
        *,
        source: str,
        target: str,
        warn_when_unhealthy: bool = False,
    ) -> None:
        """Project one owner-computed ``HealthCheck`` onto the provider report (RA-028).

        The owner names its checks its own way ("gateway"); the provider
        surface keeps its historical names ("kernel_serve"). An absent owner
        check is a hard fail — a silent skip would hide seam drift.
        """
        check = next((c for c in state.checks if c.name == source), None)
        if check is None:
            report.fail(target, f"'{source}' not reported by daemon service")
        elif check.ok:
            report.ok(target, check.detail)
        elif warn_when_unhealthy:
            report.warn(target, check.detail)
        else:
            report.fail(target, check.detail)


__all__ = ["CLIProvider"]
