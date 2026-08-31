"""Kernel serve service — LCA 进程 (:8765) 自愈,非全权管理。

ADR-0119 决定 4 把 LCA 进程入口切到 ``uv run python -m lca_kernel serve``
之后, ``lca-ops`` 不再管它的 start/stop/restart (SIGTERM 由 K6
``lca_kernel.lifecycle`` 守护)。本 service 只暴露 ``state()`` 与
``heal()``:

- ``state()`` 探测 ``/health``,报告 RUNNING / STOPPED。
- ``heal()`` 不健康时尝试 spawn 一个后台 ``lca_kernel serve`` 进程。
  ``host`` 来自 ``KernelServeConfig``,默认 ``0.0.0.0`` 让局域网能访问。

不实现 ``start / stop / restart`` —— 这些命令面应直接调
``lca-ops kernel_serve`` 拿启动命令、或由外部 supervisor 守护。
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from lca.infrastructure.cli.config import KernelServeConfig
from lca.infrastructure.cli.service import (
    HealthCheck,
    ServiceState,
    ServiceStatus,
    http_ready,
    pid_alive,
)


class KernelServeService:
    """LCA kernel serve (:8765) — health + self-heal only."""

    name = "kernel_serve"

    _SPAWN_TIMEOUT_S = 30.0
    _SPAWN_POLL_S = 0.5
    _LOG_PATH = Path("/tmp/lca-kernel.log")  # noqa: S108 — stable path for self-heal logs

    def __init__(self, config: KernelServeConfig, root: Path) -> None:
        self._config = config
        self._root = root

    @property
    def health_url(self) -> str:
        return self._config.health_url

    def state(self) -> ServiceState:
        """Observe via HTTP /health + port listener."""
        healthy = http_ready(self.health_url, timeout=1.0)
        checks = [HealthCheck("health", healthy, self.health_url)]

        if healthy:
            return ServiceState(
                status=ServiceStatus.RUNNING,
                checks=tuple(checks),
                port=self._config.port,
                detail=f"healthy at {self.health_url}",
            )
        return ServiceState(
            status=ServiceStatus.STOPPED,
            checks=tuple(checks),
            port=self._config.port,
            detail=f"not reachable at {self.health_url}",
            why="lca_kernel serve 没在跑。heal 会自动拉起。",
            next_action="./scripts/lca-ops heal",
        )

    def heal(self) -> ServiceState:
        """Probe → healthy: return. Stopped: spawn a detached ``lca_kernel serve``."""
        current = self.state()
        if current.is_running:
            return current
        if not self._spawn():
            return ServiceState(
                status=ServiceStatus.STOPPED,
                detail="spawn failed; see /tmp/lca-kernel.log",
                why="`uv run python -m lca_kernel serve` exited non-zero",
                next_action="./scripts/lca-ops logs   # journal 事实流",
            )
        return self.state()

    # ── Internals ─────────────────────────────────────────────────────

    def _spawn(self) -> bool:
        """Spawn a detached ``lca_kernel serve`` and wait until /health answers."""
        self._LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        log = self._LOG_PATH.open("ab", buffering=0)
        try:
            proc = subprocess.Popen(  # noqa: S603
                [  # noqa: S607 — controlled argv, not user-provided
                    "uv",
                    "run",
                    "python",
                    "-m",
                    "lca_kernel",
                    "serve",
                    "--profile",
                    "profiles/web-standard.yaml",
                    "--host",
                    self._config.host,
                    "--port",
                    str(self._config.port),
                    "--allow-unknown-env",
                ],
                cwd=str(self._root),
                stdout=log,
                stderr=log,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError:
            return False
        # SIGTERM 由 K6 lca_kernel.lifecycle 守护;此处只等 health ready。
        deadline = time.monotonic() + self._SPAWN_TIMEOUT_S
        while time.monotonic() < deadline:
            if not pid_alive(proc.pid):
                return False
            if http_ready(self.health_url, timeout=1.0):
                return True
            time.sleep(self._SPAWN_POLL_S)
        # timeout: 子进程可能还在 boot。让 state() 后续再判。
        return pid_alive(proc.pid)

    # ── Not supported per ADR-0119 决定 4 ─────────────────────────────

    def start(self) -> ServiceState:  # pragma: no cover - intentional stub
        raise NotImplementedError(
            "lca-ops 不提供 `lca-ops kernel_serve start`。"
            "请直接 `uv run python -m lca_kernel serve ...` "
            "或跑 `./scripts/lca-ops heal` 自愈。"
        )

    def stop(self) -> ServiceState:  # pragma: no cover - intentional stub
        raise NotImplementedError(
            "lca-ops 不 stop kernel serve (SIGTERM 由 K6 守护)。"
            "需要停时: kill <pid> 或 supervisor 介入。"
        )

    def restart(self) -> ServiceState:  # pragma: no cover - intentional stub
        raise NotImplementedError("lca-ops 不 restart kernel serve。改完代码跑 heal,新进程会起来。")


__all__ = ["KernelServeService"]
