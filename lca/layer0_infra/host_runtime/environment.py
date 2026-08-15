"""HostEnvironment — orchestrates providers to provision / destroy / inspect / heal.

One class, four operations.  Providers are composed, not inherited.
"""

from __future__ import annotations

import sys

from lca.layer0_infra.host_runtime.config import HostRuntimeConfig, UserConfig
from lca.layer0_infra.host_runtime.providers import ItemStatus, Provider, StatusReport
from lca.layer0_infra.host_runtime.providers.shared import (
    PackagesProvider,
    PathProvider,
    ToolsProvider,
    VenvProvider,
)
from lca.layer0_infra.host_runtime.providers.user import (
    CLIProvider,
    UserProvider,
    WorkspaceProvider,
)


class HostEnvironment:
    """Orchestrates all providers for the host runtime."""

    def __init__(self, config: HostRuntimeConfig) -> None:
        self.config = config
        self._shared: list[Provider] = [
            PathProvider(config),
            PackagesProvider(config),
            VenvProvider(config),
            ToolsProvider(config),
            CLIProvider(config),
        ]

    def _user_providers(self, user: UserConfig) -> list[Provider]:
        return [
            UserProvider(self.config, user),
            WorkspaceProvider(self.config, user),
        ]

    # ── provision ─────────────────────────────────────────────────────

    def provision(self, user_name: str) -> bool:
        """Provision shared layer + one user."""
        user = self._resolve_user(user_name)
        ok = True

        # Shared layer
        for provider in self._shared:
            self._log(f"[shared] {provider.name}")
            if not provider.provision():
                self._fail(f"{provider.name} provision failed")
                ok = False

        # User layer
        for provider in self._user_providers(user):
            self._log(f"[user:{user.name}] {provider.name}")
            if not provider.provision():
                self._fail(f"{provider.name} provision failed")
                ok = False

        # CLI daemon
        cli = CLIProvider(self.config, user)
        self._log(f"[user:{user.name}] cli:daemon")
        if not cli.start_daemon():
            self._fail("daemon start failed")
            ok = False

        return ok

    # ── destroy ───────────────────────────────────────────────────────

    def destroy(self, user_name: str) -> bool:
        """Stop daemon + delete user + delete workspace. Shared layer preserved."""
        user = self._resolve_user(user_name)

        # Stop daemon
        cli = CLIProvider(self.config, user)
        self._log(f"[user:{user.name}] stop daemon")
        cli.stop_daemon()

        # Delete user + workspace
        for provider in reversed(self._user_providers(user)):
            self._log(f"[user:{user.name}] destroy {provider.name}")
            provider.destroy()

        self._log("Shared resources preserved: tools, venv, CLI, PATH")
        return True

    # ── status ────────────────────────────────────────────────────────

    def status(self, user_name: str | None = None) -> list[StatusReport]:
        """Collect status from all providers."""
        reports: list[StatusReport] = []

        # Shared
        for provider in self._shared:
            reports.append(provider.status())

        # User(s)
        users = [self._resolve_user(user_name)] if user_name else self.config.users
        for user in users:
            for provider in self._user_providers(user):
                reports.append(provider.status())
            cli = CLIProvider(self.config, user)
            reports.append(cli.status())

        return reports

    # ── heal ──────────────────────────────────────────────────────────

    def heal(self, user_name: str | None = None) -> tuple[list[StatusReport], list[str]]:
        """Detect failures and attempt self-repair.

        Returns (reports, healed) where healed lists the checks that were recovered.
        """
        reports = self.status(user_name)
        healed: list[str] = []

        # Build a provider lookup: map provider name → provider instance
        providers_by_name: dict[str, Provider] = {}
        for p in self._shared:
            providers_by_name[p.name] = p
        users = [self._resolve_user(user_name)] if user_name else self.config.users
        for user in users:
            for p in self._user_providers(user):
                providers_by_name[p.name] = p
            cli = CLIProvider(self.config, user)
            providers_by_name[cli.name] = cli

        for report in reports:
            provider = providers_by_name.get(report.provider)
            if provider is None:
                continue
            for check in report.checks:
                if check.status in {ItemStatus.MISSING, ItemStatus.ERROR} and provider.heal(check):
                    healed.append(f"{report.provider}:{check.name}")

        return reports, healed

    # ── helpers ───────────────────────────────────────────────────────

    def _resolve_user(self, name: str) -> UserConfig:
        user = self.config.find_user(name)
        if user is None:
            user = UserConfig(name=name)
            self.config.users.append(user)
        return user

    @staticmethod
    def _log(msg: str) -> None:
        sys.stdout.write(f"\033[1;36m[lca-host]\033[0m {msg}\n")
        sys.stdout.flush()

    @staticmethod
    def _fail(msg: str) -> None:
        sys.stderr.write(f"\033[1;31m  ❌ {msg}\033[0m\n")
        sys.stderr.flush()
