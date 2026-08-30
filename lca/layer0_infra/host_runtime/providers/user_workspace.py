"""Host-runtime provider for one system user's workspace directories and ownership."""

from __future__ import annotations

from pathlib import Path

from lca.layer0_infra.host_runtime.config import HostRuntimeConfig, UserConfig
from lca.layer0_infra.host_runtime.providers import Provider, StatusReport


class WorkspaceProvider(Provider):
    """Provision the user home, outputs, state directories, and their ownership."""

    def __init__(self, config: HostRuntimeConfig, user: UserConfig) -> None:
        super().__init__(config)
        self.user = user

    @property
    def name(self) -> str:
        """Return the provider's stable diagnostics identity."""
        return f"workspace:{self.user.name}"

    def provision(self) -> bool:
        """Create all user workspace paths and apply group-sticky access permissions."""
        home = self.user.home
        self.run_sudo(["mkdir", "-p", home])
        self.run_sudo(["mkdir", "-p", self.user.outputs_dir])
        self.run_sudo(["mkdir", "-p", self.user.state_dir])
        self.run_sudo(["chown", "-R", f"{self.user.name}:{self.user.name}", home])
        self.run_sudo(["chmod", "2770", home])
        return True

    def destroy(self) -> bool:
        """Remove the user home tree when it remains after account cleanup."""
        home = Path(self.user.home)
        if home.is_dir():
            self.run_sudo(["rm", "-rf", self.user.home])
        return not home.is_dir()

    def status(self) -> StatusReport:
        """Report directory existence and effective mode for the user home."""
        report = StatusReport(self.name)
        home = Path(self.user.home)
        if not home.is_dir():
            report.fail("home", f"{self.user.home} missing")
            return report
        report.ok("home", self.user.home)
        outputs = Path(self.user.outputs_dir)
        if outputs.is_dir():
            report.ok("outputs", self.user.outputs_dir)
        else:
            report.fail("outputs")
        report.ok("permissions", f"{home.stat().st_mode:#o}")
        return report


__all__ = ["WorkspaceProvider"]
