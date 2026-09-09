"""Kernel serve service — LCA 进程 (:8765) 健康观察 + spawn 入口。

ADR-0119 决定 4 把 LCA 进程入口切到 ``uv run python -m lca_kernel serve``
之后, ``lca-ops`` 不再管它的 start/stop/restart (SIGTERM 由 K6
``lca_kernel.lifecycle`` 守护)。本 service 只暴露两个职责:

- ``state()`` 探测 ``/health``,报告 RUNNING / STOPPED。
- ``spawner()`` 返回 :class:`KernelServeSpawner` 实例,CLI 子命令直接调
  ``spawner.run()`` 拿结构化 :class:`SpawnResult`。

不实现 ``start / stop / restart / heal`` —— 单一职责原则。SIGTERM 现有
PID 是 ``kernel-restart`` CLI 子命令内联职责,不属于本 service。

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
- 5 个原子步骤聚合为结构化 ``SpawnResult(ok, failed_stage, steps, pid,
  port, stderr_path, duration_ms, actionable)``。
- stderr 每 spawn 独立落盘到 ``/tmp/lca-kernel.stderr.<pid>.<timestamp>.log``,
  保留最近 5 个文件;并发 spawn 不会交错。
- CLI 消费方(如 ``kernel-restart`` 与 ``stack_heal``)原样透传
  ``actionable`` 到 console / ServiceState,不 fallback 到"kernel 没在跑,去 heal"。

Readiness(post-0213 PR-2):
- ``state()`` 用 ``health_body_ok``(HTTP 200 + body ``status == "ok"``)。
- HTTP 200 配 ``status: degraded`` / ``loading`` 不再报 healthy。
"""

from __future__ import annotations

from pathlib import Path

from lca.infrastructure.cli.config.config import KernelServeConfig
from lca.infrastructure.cli.service.service import (
    HealthCheck,
    ServiceState,
    ServiceStatus,
    health_body_ok,
)
from lca.infrastructure.cli.services.kernel.spawner import KernelServeSpawner

# Hosts that bind-all. Used by spawner's LAN probe to decide whether to
# re-check the Next.js proxy's expected URL after loopback /health is ready.
_BIND_ALL_HOSTS = frozenset({"0.0.0.0", "::"})  # noqa: S104 — see KernelServeConfig


class KernelServeService:
    """LCA kernel serve (:8765) — health observation + spawner factory.

    Single responsibility: observe /health and expose the spawner. CLI
    subcommands drive ``SIGTERM`` and ``stack.heal`` orchestration
    themselves; this service never re-implements that loop.
    """

    name = "kernel_serve"

    def __init__(self, config: KernelServeConfig, root: Path) -> None:
        self._config = config
        self._root = root
        self._spawner = KernelServeSpawner(config=config, root=root)

    @property
    def health_url(self) -> str:
        return self._spawner.health_url

    def spawner(self) -> KernelServeSpawner:
        """Return the spawner instance owned by this service.

        CLI subcommands call ``spawner().run()`` and surface
        ``SpawnResult.actionable`` directly; this avoids the legacy
        ``heal() / restart()`` shim that hid failure reasons behind
        "kernel not running, run heal" fallbacks.
        """
        return self._spawner

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
            why="lca_kernel serve 没在跑。",
            next_action="./scripts/lca-ops kernel-restart",
        )

    # ── Not supported per ADR-0119 决定 4 ─────────────────────────────

    def start(self) -> ServiceState:  # pragma: no cover - intentional stub
        raise NotImplementedError(
            "lca-ops 不提供 `lca-ops kernel_serve start`。"
            "请直接 `uv run python -m lca_kernel serve ...` "
            "或跑 `./scripts/lca-ops kernel-restart`。"
        )

    def stop(self) -> ServiceState:  # pragma: no cover - intentional stub
        raise NotImplementedError(
            "lca-ops 不提供 `lca-ops kernel_serve stop`。"
            "SIGTERM 由 K6 ``lca_kernel.lifecycle`` 守护。"
        )

    def heal(self) -> ServiceState:  # pragma: no cover - intentional stub
        raise NotImplementedError(
            "KernelServeService 不提供 heal()。改用 `kernel-restart` "
            "子命令或 `stack.heal` 走 `spawner().run()`。"
        )

    def restart(self) -> ServiceState:  # pragma: no cover - intentional stub
        raise NotImplementedError(
            "KernelServeService 不提供 restart()。改用 `./scripts/lca-ops kernel-restart` 子命令。"
        )


__all__ = ["KernelServeService"]
