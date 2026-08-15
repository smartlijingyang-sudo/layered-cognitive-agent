"""DSH SDK — installed in the shared LCA venv on the sandbox-user side.

Ops checks whether the SDK is importable from the venv's Python and
prompts the operator to install it when missing.  DSH execution is
delegated to the machine transport (MachineDshRuntime), so the SDK
must be available where the daemon runs — not in the gateway venv.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from lca.layer0_infra.ops.config import DshConfig
from lca.layer0_infra.ops.service import HealthCheck, ServiceState, ServiceStatus


@dataclass(frozen=True, slots=True)
class DshObservation:
    """Read-only snapshot of the DSH SDK installation."""

    venv_exists: bool
    sdk_importable: bool
    install_script_exists: bool


class DshProbe(Protocol):
    """Host probes. Injected so status tests do not need filesystem."""

    def observe(self) -> DshObservation: ...


class SystemDshProbe:
    """Filesystem + subprocess on this host."""

    def __init__(self, config: DshConfig, root: Path) -> None:
        self._config = config
        self._root = root

    def observe(self) -> DshObservation:
        py = self._config.sdk_python
        venv_exists = py.is_file()
        sdk_importable = False
        if venv_exists:
            sdk_importable = self._check_import(py)
        return DshObservation(
            venv_exists=venv_exists,
            sdk_importable=sdk_importable,
            install_script_exists=(self._root / self._config.install_script).is_file(),
        )

    def _check_import(self, python: Path) -> bool:
        try:
            result = subprocess.run(
                [str(python), "-c", "from deepseek_harness import DeepSeekHarness"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
        return result.returncode == 0


class DshService:
    """Observe and repair the DSH SDK installation in the shared venv."""

    def __init__(
        self,
        config: DshConfig,
        root: Path | None = None,
        probe: DshProbe | None = None,
    ) -> None:
        self.name = "dsh"
        self._config = config
        self._root = root or Path.cwd()
        self._probe: DshProbe = probe or SystemDshProbe(config, self._root)

    def start(self) -> ServiceState:
        return self.state()

    def stop(self) -> ServiceState:
        current = self.state()
        return ServiceState(
            status=current.status,
            checks=current.checks,
            detail=current.detail,
            why="DSH SDK is declarative; lca-ops does not remove it",
        )

    def restart(self) -> ServiceState:
        return self.heal()

    def ensure_ready(self) -> bool:
        current = self.state()
        if current.is_running:
            return False
        obs = self._probe.observe()
        if not obs.install_script_exists or not obs.venv_exists:
            return False
        return self._install()

    def state(self) -> ServiceState:
        obs = self._probe.observe()
        checks = (
            HealthCheck("venv", obs.venv_exists, str(self._config.sdk_python)),
            HealthCheck("sdk", obs.sdk_importable, self._config.sdk_package),
            HealthCheck("install_script", obs.install_script_exists, self._config.install_script),
        )

        if not obs.venv_exists:
            return ServiceState(
                status=ServiceStatus.STOPPED,
                checks=checks,
                detail="LCA venv missing",
                why=f"{self._config.venv_dir} not found",
                next_action="./scripts/lca-ops provision",
            )

        if not obs.sdk_importable:
            return ServiceState(
                status=ServiceStatus.STOPPED,
                checks=checks,
                detail="DSH SDK not installed",
                why=f"{self._config.sdk_package} not importable from {self._config.venv_dir}",
                next_action=self._config.install_cmd,
            )

        return ServiceState(
            status=ServiceStatus.RUNNING,
            checks=checks,
            detail=f"SDK in {self._config.venv_dir}",
        )

    def heal(self) -> ServiceState:
        current = self.state()
        if current.is_running:
            return current
        obs = self._probe.observe()
        if not obs.venv_exists or not obs.install_script_exists:
            return current
        self._install()
        return self.state()

    def _install(self) -> bool:
        script = self._root / self._config.install_script
        try:
            result = subprocess.run(
                ["bash", str(script)],
                cwd=str(self._root),
                capture_output=True,
                text=True,
                timeout=300,
                env={**_base_env(), "VENV_DIR": str(self._config.venv_dir)},
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
        return result.returncode == 0


def _base_env() -> dict[str, str]:
    import os

    return {k: v for k, v in os.environ.items() if k not in {"VIRTUAL_ENV"}}
