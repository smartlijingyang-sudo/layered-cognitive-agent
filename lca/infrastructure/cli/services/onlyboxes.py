"""Onlyboxes terminal runtime — worker image + systemd drop-in.

status must notice when the worker is still on the upstream
``onlyboxes-runtime:default`` image (no officecli, WORKDIR /workspace)
instead of ``onlyboxes-terminal-local:lca`` (ADR-0054, GuestLayout).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from lca.infrastructure.cli.config import OnlyboxesConfig
from lca.infrastructure.cli.service import HealthCheck, ServiceState, ServiceStatus


@dataclass(frozen=True, slots=True)
class OnlyboxesObservation:
    """Read-only snapshot of the host Onlyboxes runtime."""

    image_present: bool
    dropin_text: str | None
    legacy_dropin_exists: bool
    worker_env: str
    stale_default: int
    worker_active: bool
    unit_exists: bool


class OnlyboxesProbe(Protocol):
    """Host probes. Injected so status tests do not need docker/systemd."""

    def observe(self) -> OnlyboxesObservation: ...

    def configure(self) -> bool: ...


class SystemOnlyboxesProbe:
    """docker + systemd + drop-in files on this host."""

    def __init__(self, config: OnlyboxesConfig, root: Path) -> None:
        self._config = config
        self._root = root

    def observe(self) -> OnlyboxesObservation:
        dropin = self._config.dropin_path
        dropin_text = dropin.read_text(encoding="utf-8") if dropin.is_file() else None
        return OnlyboxesObservation(
            image_present=self._cmd_ok(["docker", "image", "inspect", self._config.terminal_image]),
            dropin_text=dropin_text,
            legacy_dropin_exists=self._config.legacy_dropin_dir.exists(),
            worker_env=self._cmd_out(
                ["systemctl", "show", self._config.worker_service, "-p", "Environment", "--value"]
            ),
            stale_default=self._stale_count(),
            worker_active=self._cmd_out(
                ["systemctl", "is-active", self._config.worker_service]
            ).strip()
            == "active",
            unit_exists=self._cmd_ok(["systemctl", "cat", self._config.worker_service]),
        )

    def configure(self) -> bool:
        script = self._root / self._config.configure_script
        if not script.is_file():
            return False
        try:
            result = subprocess.run(
                ["bash", str(script)],
                cwd=self._root,
                capture_output=True,
                text=True,
                timeout=180,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
        return result.returncode == 0

    def _stale_count(self) -> int:
        out = self._cmd_out(
            ["docker", "ps", "-q", "--filter", f"ancestor={self._config.stale_image}"]
        )
        return len([line for line in out.splitlines() if line.strip()])

    @staticmethod
    def _cmd_ok(cmd: list[str]) -> bool:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
        return result.returncode == 0

    @staticmethod
    def _cmd_out(cmd: list[str]) -> str:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return ""
        return result.stdout if result.returncode == 0 else result.stdout or ""


class OnlyboxesService:
    """Observe and repair the Onlyboxes terminalExec runtime pin."""

    def __init__(
        self,
        config: OnlyboxesConfig,
        root: Path | None = None,
        probe: OnlyboxesProbe | None = None,
    ) -> None:
        self.name = "onlyboxes"
        self._config = config
        self._root = root or Path.cwd()
        self._probe: OnlyboxesProbe = probe or SystemOnlyboxesProbe(config, self._root)

    def start(self) -> ServiceState:
        return self.heal()

    def stop(self) -> ServiceState:
        current = self.state()
        return ServiceState(
            status=current.status,
            checks=current.checks,
            detail=current.detail,
            why="onlyboxes worker is host-managed; lca-ops does not stop it",
        )

    def restart(self) -> ServiceState:
        return self.heal()

    def ensure_ready(self) -> bool:
        current = self.state()
        if current.is_running and not current.next_action:
            return False
        obs = self._probe.observe()
        if not obs.image_present:
            return False
        return self._probe.configure()

    def state(self) -> ServiceState:
        obs = self._probe.observe()
        cfg = self._config
        dropin_ok = _mentions_image(obs.dropin_text or "", cfg.env_key, cfg.terminal_image)
        env_ok = _mentions_image(obs.worker_env, cfg.env_key, cfg.terminal_image)
        checks = (
            HealthCheck("image", obs.image_present, cfg.terminal_image),
            HealthCheck("dropin", dropin_ok, str(cfg.dropin_path)),
            HealthCheck("legacy_dropin", not obs.legacy_dropin_exists, str(cfg.legacy_dropin_dir)),
            HealthCheck("worker_env", env_ok, cfg.env_key),
            HealthCheck("stale_default", obs.stale_default == 0, f"count={obs.stale_default}"),
            HealthCheck("worker", obs.worker_active, cfg.worker_service),
        )

        if not obs.image_present:
            return ServiceState(
                status=ServiceStatus.STOPPED,
                checks=checks,
                detail="LCA terminal image missing",
                why=f"{cfg.terminal_image} is not built — worker cannot pin officecli runtime",
                next_action=cfg.build_and_configure_cmd,
            )

        if not obs.unit_exists:
            return ServiceState(
                status=ServiceStatus.STOPPED,
                checks=checks,
                detail="worker unit missing",
                why=f"{cfg.worker_service} is not installed on this host",
                next_action="",
            )

        needs_configure = (
            not dropin_ok or not env_ok or obs.legacy_dropin_exists or obs.stale_default > 0
        )
        if needs_configure:
            why = _configure_why(obs, dropin_ok, env_ok)
            return ServiceState(
                status=ServiceStatus.DEGRADED if obs.worker_active else ServiceStatus.STOPPED,
                checks=checks,
                detail="terminal runtime not pinned",
                why=why,
                next_action=cfg.configure_cmd,
            )

        if not obs.worker_active:
            return ServiceState(
                status=ServiceStatus.STOPPED,
                checks=checks,
                detail="worker not running",
                why=f"{cfg.worker_service} is inactive",
                next_action=f"sudo systemctl start {cfg.worker_service}",
            )

        return ServiceState(
            status=ServiceStatus.RUNNING,
            checks=checks,
            detail=f"runtime {cfg.terminal_image}",
        )

    def heal(self) -> ServiceState:
        current = self.state()
        if current.is_running and not current.next_action:
            return current
        obs = self._probe.observe()
        if not obs.image_present or not obs.unit_exists:
            return current
        self._probe.configure()
        return self.state()


def _mentions_image(text: str, key: str, image: str) -> bool:
    return f"{key}={image}" in text


def _configure_why(obs: OnlyboxesObservation, dropin_ok: bool, env_ok: bool) -> str:
    parts: list[str] = []
    if not dropin_ok:
        parts.append("systemd drop-in missing or not pointing at LCA terminal image")
    if not env_ok:
        parts.append("worker env still on upstream runtime (no officecli)")
    if obs.legacy_dropin_exists:
        parts.append("legacy drop-in path exists and is ignored by systemd")
    if obs.stale_default > 0:
        parts.append(f"{obs.stale_default} terminalExec session(s) still on :default")
    return "; ".join(parts)
