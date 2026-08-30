"""Abstract provider + status types.

Every subsystem (user, workspace, tools, venv, path, packages, cli)
is a Provider with three operations: provision, destroy, status.
"""

# ruff: noqa: S603, S607

from __future__ import annotations

import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from lca.infrastructure.host_runtime.config import HostRuntimeConfig


class ItemStatus(Enum):
    OK = "ok"
    MISSING = "missing"
    ERROR = "error"
    WARN = "warn"


@dataclass
class CheckResult:
    name: str
    status: ItemStatus
    detail: str = ""


@dataclass
class StatusReport:
    provider: str
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def all_ok(self) -> bool:
        return all(c.status == ItemStatus.OK for c in self.checks)

    def ok(self, name: str, detail: str = "") -> None:
        self.checks.append(CheckResult(name, ItemStatus.OK, detail))

    def fail(self, name: str, detail: str = "") -> None:
        self.checks.append(CheckResult(name, ItemStatus.MISSING, detail))

    def warn(self, name: str, detail: str = "") -> None:
        self.checks.append(CheckResult(name, ItemStatus.WARN, detail))


class Provider(ABC):
    """Base class for all host runtime subsystems."""

    def __init__(self, config: HostRuntimeConfig) -> None:
        self.config = config

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def provision(self) -> bool: ...

    def destroy(self) -> bool:
        """Default: no-op. Override for providers that own resources."""
        return True

    @abstractmethod
    def status(self) -> StatusReport: ...

    def heal(self, failed_check: CheckResult) -> bool:
        """Attempt to recover a failed check. Default: cannot heal.

        Override in providers that know how to self-repair (e.g. restart a daemon).
        Returns True if the issue was resolved.
        """
        return False

    # ── shared helpers ───────────────────────────────────────────────

    @staticmethod
    def run(
        cmd: list[str], *, check: bool = False, sudo: bool = False
    ) -> subprocess.CompletedProcess[str]:
        if sudo:
            cmd = ["sudo", "-n", *cmd]
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=check,
            timeout=300,
        )

    @staticmethod
    def run_sudo(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        """sudo with password from .lobehub-stack/sudo.pass."""
        pass_file = Path(".lobehub-stack/sudo.pass")
        if pass_file.is_file():
            pw = pass_file.read_text().strip()
            return subprocess.run(
                ["sudo", "-S", "-p", "", *cmd],
                input=pw,
                capture_output=True,
                text=True,
                timeout=300,
            )
        return subprocess.run(
            ["sudo", "-n", *cmd],
            capture_output=True,
            text=True,
            timeout=300,
        )

    @staticmethod
    def exists(path: str | Path) -> bool:
        return Path(path).exists()

    @staticmethod
    def which(name: str) -> str | None:
        result = subprocess.run(
            ["which", name],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else None
