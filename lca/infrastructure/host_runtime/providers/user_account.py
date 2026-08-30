"""Host-runtime provider for system-user lifecycle operations."""

from __future__ import annotations

import time

from lca.infrastructure.host_runtime.config import HostRuntimeConfig, UserConfig
from lca.infrastructure.host_runtime.providers import Provider, StatusReport


class UserProvider(Provider):
    """Provision and destroy one system user, including stale-group cleanup."""

    def __init__(self, config: HostRuntimeConfig, user: UserConfig) -> None:
        super().__init__(config)
        self.user = user

    @property
    def name(self) -> str:
        """Return the provider's stable diagnostics identity."""
        return f"user:{self.user.name}"

    @property
    def _exists(self) -> bool:
        return bool(self.run(["id", "-u", self.user.name]).returncode == 0)

    def provision(self) -> bool:
        """Create the configured system user when it is not already present."""
        if self._exists:
            return True
        self.run_sudo(["groupdel", self.user.name])
        result = self.run_sudo(
            [
                "useradd",
                "--system",
                "--create-home",
                "--home-dir",
                self.user.home,
                "--shell",
                self.user.shell,
                self.user.name,
            ]
        )
        return bool(result.returncode == 0)

    def destroy(self) -> bool:
        """Stop user processes and remove the user, home directory, and stale group."""
        if not self._exists:
            return True
        self.run(["pkill", "-9", "-u", self.user.name])
        time.sleep(1)
        self.run_sudo(["userdel", "-r", self.user.name])
        self.run_sudo(["groupdel", self.user.name])
        return not self._exists

    def status(self) -> StatusReport:
        """Report whether the configured system user is available."""
        report = StatusReport(self.name)
        if self._exists:
            result = self.run(["id", self.user.name])
            report.ok(self.user.name, result.stdout.strip())
        else:
            report.fail(self.user.name, "does not exist")
        return report


__all__ = ["UserProvider"]
