"""Kernel serve service — LCA 进程 (:8765) 自愈,非全权管理。

ADR-0119 决定 4 把 LCA 进程入口切到 ``uv run python -m lca_kernel serve``
之后, ``lca-ops`` 不再管它的 start/stop/restart (SIGTERM 由 K6
``lca_kernel.lifecycle`` 守护)。本 service 只暴露 ``state()`` 与
``heal()``:

- ``state()`` 探测 ``/health``,报告 RUNNING / STOPPED。
- ``heal()`` 不健康时尝试 spawn 一个后台 ``lca_kernel serve`` 进程。
  ``host`` 来自 ``KernelServeConfig``,默认 ``0.0.0.0`` 让局域网能访问。
  spawn 成功后会再探活 Next.js proxy 配置中的 LAN URL(LCA_GATEWAY_PUBLIC_URL
  / OPENAI_PROXY_URL),防止"loopback 通 LAN 不通 → 前端打过来 500"静默踩坑。

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
"""

from __future__ import annotations

import contextlib
import subprocess
import sys
import time
from pathlib import Path
from typing import Protocol, cast

from lca.infrastructure.cli.config.config import KernelServeConfig
from lca.infrastructure.cli.service.service import (
    HealthCheck,
    ServiceState,
    ServiceStatus,
    http_ready,
    pid_alive,
)
from lca.infrastructure.cli.services.process.utils import (
    find_pid_by_argv,
    port_listening,
)

# Hosts that bind-all. Used by _spawn's LAN probe to decide whether to
# re-check the Next.js proxy's expected URL after loopback /health is ready.
_BIND_ALL_HOSTS = frozenset({"0.0.0.0", "::"})  # noqa: S104 — see KernelServeConfig


class _ProcessLike(Protocol):
    def send_signal(self, sig: int) -> None: ...


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
            # 等端口彻底空闲(给 K6 留出 dispose 时间)
            deadline = time.monotonic() + 10.0
            while time.monotonic() < deadline:
                if not port_listening(self._config.port):
                    break
                time.sleep(self._SPAWN_POLL_S)
        return self.heal()

    # ── Internals ─────────────────────────────────────────────────────

    def _spawn(self) -> bool:
        """Spawn a detached ``lca_kernel serve`` and wait until /health answers."""
        preflight = self._preflight_jwt_secret()
        if preflight == "block":
            return False
        if preflight == "warn":
            print(
                "[WARN] lca-ops: JWT key auto-generation (dev_mode=true); "
                "key changes on every kernel restart — not safe for multi-replica.",
                flush=True,
            )
        self._LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        log = self._LOG_PATH.open("ab", buffering=0)
        try:
            # 用 sys.executable(当前 lca-ops 解释器)直接 spawn;
            # 不走 uv run —— 见 module docstring "spawn 路径经验"。
            proc = subprocess.Popen(  # noqa: S603
                [  # noqa: S607 — controlled argv, not user-provided
                    sys.executable,
                    "-m",
                    "lca_kernel",
                    "serve",
                    "--profile",
                    self._config.profile,
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
                # 不设 start_new_session=True:让子进程保持 lca-ops 的
                # process group,SIGINT 能正确传给 uvicorn worker。
                # close_fds=True 确保不继承无关 fd。
            )
        except OSError:
            return False
        # SIGTERM 由 K6 lca_kernel.lifecycle 守护;此处只等 health ready。
        deadline = time.monotonic() + self._SPAWN_TIMEOUT_S
        while time.monotonic() < deadline:
            if not pid_alive(proc.pid):
                return False
            if http_ready(self.health_url, timeout=1.0) and (
                self._config.host not in _BIND_ALL_HOSTS or self._probe_proxy_lan()
            ):
                return True
            time.sleep(self._SPAWN_POLL_S)
        # timeout: 子进程可能还在 boot。让 state() 后续再判。
        return pid_alive(proc.pid)

    def _probe_proxy_lan(self) -> bool:
        """Probe the Next.js proxy's expected kernel URL (LAN).

        Reads ``LCA_GATEWAY_PUBLIC_URL`` (or ``OPENAI_PROXY_URL`` as
        fallback — both are read by lobehub-ui) and GETs its ``/health``.
        Returns True if reachable within 2s, False otherwise. When the
        env var is unset, returns True (operator explicitly chose
        loopback-only or hasn't deployed lobehub-ui yet).
        """
        import os
        import urllib.parse

        candidates = ("LCA_GATEWAY_PUBLIC_URL", "OPENAI_PROXY_URL")
        target = next((os.environ[k] for k in candidates if os.environ.get(k)), "")
        if not target:
            return True
        parsed = urllib.parse.urlparse(target)
        if not parsed.hostname or not parsed.port:
            return True
        lan_health = f"http://{parsed.hostname}:{parsed.port}/health"
        if lan_health == self.health_url:
            return True  # 同一 host:port,已经探活过了
        if http_ready(lan_health, timeout=2.0):
            return True
        print(
            f"[FAIL] lca-ops: kernel serve loopback healthy at {self.health_url} "
            f"but Next.js proxy target {lan_health} unreachable. "
            f"Set LCA_KERNEL_HOST=0.0.0.0 or fix the LAN route.",
            flush=True,
        )
        return False

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

    def ensure_ready(self) -> bool:  # pragma: no cover - intentional stub
        return False

    # ── Preflight: JWT secret injection ──────────────────────────────

    def _preflight_jwt_secret(self) -> str:
        """Inspect the active Profile's JWT config + ambient env before spawn.

        Returns:
            "ok"     — neither blocks nor warns (production key injected).
            "warn"   — dev_mode=true; keypair will be auto-generated in-process.
            "block"  — neither dev-mode nor a usable LCA_JWT_SECRET; refuse to
                       spawn so the operator does not hit another 500.

        The check mirrors the runtime contract enforced by
        ``lca-webserver-jwt-keys``: ``jwt.private_pem`` may be a literal,
        a ``{from_env: NAME}`` reference (Profile-harness-resolved at boot),
        or fall back to ``jwt.dev_mode: true``.
        """
        import os

        try:
            import yaml

            profile_path = Path(self._config.profile)
            if not profile_path.is_absolute():
                profile_path = self._root / profile_path
            data = yaml.safe_load(profile_path.read_text())
        except (OSError, yaml.YAMLError) as exc:
            print(
                f"[WARN] lca-ops: cannot read profile {self._config.profile} for JWT "
                f"preflight ({exc}); skipping check",
                flush=True,
            )
            return "ok"

        def _bundles_list(node: object) -> list[object]:
            if isinstance(node, dict):
                return list(node.get("bundles", []))
            return []

        def _walk_for_jwt(node: object) -> dict[str, object] | None:
            if isinstance(node, dict):
                if node.get("id") == "lca-webserver-jwt-keys":
                    cfg = node.get("config") or {}
                    return cfg if isinstance(cfg, dict) else None
                for v in node.values():
                    found = _walk_for_jwt(v)
                    if found is not None:
                        return found
            elif isinstance(node, list):
                for item in node:
                    found = _walk_for_jwt(item)
                    if found is not None:
                        return found
            return None

        jwt_cfg = _walk_for_jwt(data)
        if jwt_cfg is None:
            # JWT plugin not in this profile — assume the operator knows what
            # they are doing and let the kernel's own boot-time check fire.
            return "ok"

        if bool(jwt_cfg.get("dev_mode")):
            return "warn"

        private_pem = jwt_cfg.get("private_pem")
        if isinstance(private_pem, dict) and "from_env" in private_pem:
            env_name = str(private_pem["from_env"])
            if os.environ.get(env_name):
                return "ok"
            print(
                f"[ERROR] lca-ops: Profile requires `{env_name}` for the JWT signing "
                f"key, but the env var is not set. Refusing to spawn kernel — set the "
                f"env var (or temporarily add `jwt.dev_mode: true` to the Profile) and "
                f"retry. See docs/notes/jwt-secret-injection-via-profile.md.",
                flush=True,
            )
            return "block"

        if isinstance(private_pem, str) and private_pem.strip():
            return "ok"

        print(
            "[ERROR] lca-ops: Profile has neither `jwt.private_pem` nor `jwt.dev_mode`. "
            "Refusing to spawn kernel. Configure one of the two and retry. See "
            "docs/notes/jwt-secret-injection-via-profile.md.",
            flush=True,
        )
        return "block"


__all__ = ["KernelServeService"]
