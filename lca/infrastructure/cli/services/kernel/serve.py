"""Kernel serve service — LCA 进程 (:8765) 自愈,非全权管理。

ADR-0119 决定 4 把 LCA 进程入口切到 ``uv run python -m lca_kernel serve``
之后, ``lca-ops`` 不再管它的 start/stop/restart (SIGTERM 由 K6
``lca_kernel.lifecycle`` 守护)。本 service 只暴露 ``state()`` 与
``heal()``:

- ``state()`` 探测 ``/health``,报告 RUNNING / STOPPED。
- ``heal()`` 不健康时委托 :class:`KernelServeSpawner` 拉起后台
  ``lca_kernel serve`` 进程。``host`` 来自 ``KernelServeConfig``,默认
  ``0.0.0.0`` 让局域网能访问。

不实现 ``start / stop / restart`` —— 这些命令面应直接调
``lca-ops kernel_serve`` 拿启动命令、或由外部 supervisor 守护。

spawn 路径经验(2026-09-09):
- 用 ``sys.executable``(当前 ``lca-ops`` 解释器,即 ``/opt/lca/venv/bin/python``)
  直接 Popen,**不**走 ``uv run``。``uv run`` 创独立 venv / 用 lockfile
  缓存,不与 ``/opt/lca/venv`` 同步,导致 ``ModuleNotFoundError: No module
  named 'cordis'`` 这种"日志空、立即退出"的鬼火问题。
- 任何手动 ``pip install`` 到 ``/home/lichao/.local/`` 的包无效;必须
  ``/opt/lca/venv/bin/pip install``(详见 docs/operations/venv.md)。
- spawn 后 30s 内未 ready 视为失败;SIGTERM 由 K6 ``lca_kernel.lifecycle``
  守护,本 service 只负责 spawn + 等 /health。

5 原子 step 与 SpawnResult(2026-09-09):
- 由 :class:`KernelServeSpawner` 实现,见 ADR-0213 §决定 1–3。
- ``_spawn() -> bool`` 的旧实现已删除;5 个原子步骤聚合为结构化
  ``SpawnResult(ok, failed_stage, steps, pid, port, stderr_path,
  duration_ms, actionable)``,``heal()`` 原样透传到 ``ServiceState``,
  不再 fallback 到"kernel 没在跑,去 heal"。
- stderr 每 spawn 独立落盘到 ``/tmp/lca-kernel.stderr.<pid>.<timestamp>.log``,
  保留最近 5 个文件;并发 spawn 不会交错。
"""

from __future__ import annotations

import contextlib
import time
from pathlib import Path
from typing import Protocol, cast

from lca.infrastructure.cli.config.config import KernelServeConfig
from lca.infrastructure.cli.service.service import (
    HealthCheck,
    ServiceState,
    ServiceStatus,
    health_body_ok,
)
from lca.infrastructure.cli.services.kernel.spawner import KernelServeSpawner
from lca.infrastructure.cli.services.process.utils import find_pid_by_argv, port_listening

# Hosts that bind-all. Used by spawner's LAN probe to decide whether to
# re-check the Next.js proxy's expected URL after loopback /health is ready.
_BIND_ALL_HOSTS = frozenset({"0.0.0.0", "::"})  # noqa: S104 — see KernelServeConfig


class _ProcessLike(Protocol):
    def send_signal(self, sig: int) -> None: ...


class KernelServeService:
    """LCA kernel serve (:8765) — health + self-heal only."""

    name = "kernel_serve"

    def __init__(self, config: KernelServeConfig, root: Path) -> None:
        self._config = config
        self._root = root
        self._spawner = KernelServeSpawner(config=config, root=root)

    @property
    def health_url(self) -> str:
        return self._spawner.health_url

    def state(self) -> ServiceState:
        """Observe via HTTP /health + port listener.

        Readiness requires HTTP 200 AND body ``status == "ok"``
        (post-0213 PR-2). A 200 with degraded / partial payload must not
        report the kernel as healthy.
        """
        healthy = health_body_ok(self.health_url, timeout=1.0)
        checks = (HealthCheck("health", healthy, self.health_url),)
        if healthy:
            return ServiceState(
                status=ServiceStatus.RUNNING,
                checks=checks,
                detail=f"healthy at {self.health_url}",
            )
        return ServiceState(
            status=ServiceStatus.STOPPED,
            checks=checks,
            detail=f"not reachable at {self.health_url}",
            why="lca_kernel serve 没在跑。heal 会自动拉起。",
            next_action="./scripts/lca-ops heal",
        )

    def heal(self) -> ServiceState:
        """Probe → healthy: return. Stopped: delegate to KernelServeSpawner."""
        current = self.state()
        if current.is_running:
            return current
        result = self._spawner.run()
        if not result.ok:
            stage = result.failed_stage or "unknown"
            err = next((s.error for s in result.steps if not s.ok), "unknown")
            return ServiceState(
                status=ServiceStatus.STOPPED,
                detail=f"spawn failed at stage={stage}: {err}",
                why=f"`lca_kernel serve` stage={stage} error={err}",
                next_action=result.actionable
                or (
                    f"Inspect stderr: {result.stderr_path}"
                    if result.stderr_path
                    else "./scripts/lca-ops logs   # journal 事实流"
                ),
            )
        return self.state()

    def restart(self) -> ServiceState:
        """SIGTERM 现有 PID(让 K6 dispose)→ 等端口空 → spawn 新进程。

        ADR-0119 决定 4: lca-ops 不长管 kernel_serve;本 ``restart``
        是给"改完代码 / 换 profile / 强制刷新"用的本地快捷方式。
        操作员 SIGTERM 之后由 K6 dispose, 然后本方法负责 spawn 新进程。
        """
        existing_pid = find_pid_by_argv("lca_kernel", "serve")
        if existing_pid is not None:
            with contextlib.suppress(ProcessLookupError):
                cast("_ProcessLike", existing_pid).send_signal(15)  # SIGTERM → K6 dispose → exit
            # 等端口彻底空闲(给 K6 留出 dispose time)
            deadline = time.monotonic() + 10.0
            while time.monotonic() < deadline:
                if not port_listening(self._config.port):
                    break
                time.sleep(0.5)
        return self.heal()

    # ── Not supported per ADR-0119 决定 4 ─────────────────────────────

    def start(self) -> ServiceState:  # pragma: no cover - intentional stub
        raise NotImplementedError(
            "lca-ops 不提供 `lca-ops kernel_serve start`。"
            "请直接 `uv run python -m lca_kernel serve ...` "
            "或跑 `./scripts/lca-ops heal` 自愈。"
        )

    def stop(self) -> ServiceState:  # pragma: no cover - intentional stub
        raise NotImplementedError(
            "lca-ops 不提供 `lca-ops kernel_serve stop`。"
            "SIGTERM 由 K6 ``lca_kernel.lifecycle`` 守护。"
        )


__all__ = ["KernelServeService"]
