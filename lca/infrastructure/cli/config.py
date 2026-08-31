"""Unified configuration — single YAML SSOT.

One config object rules them all. Pydantic-validated, env-overlayable.
Replaces: stack.yaml + lca-host.yaml + .env.lca fragmentation.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, Field


class KernelServeConfig(BaseModel):
    """LCA kernel serve (Starlette :8765) 网络配置 — ADR-0119 决定 4。

    LCA 进程本身**不**由本配置驱动(spawn 命令、`watch` 路径在 ADR-0119
    决定 4 中删除);LCA 进程入口是 ``python -m lca_kernel serve``,SIGTERM
    由 K6 ``lca_kernel.lifecycle`` 守护。本类仅保留 daemon 等其他服务需要
    的网络配置(host / port / health_path),用于构造 ``base_url`` /
    ``health_url`` 与 ``lca-ops heal`` 自动拉起 LCA 进程。

    ``host`` 默认 ``0.0.0.0`` 让 kernel serve 在局域网可访问;daemon 走
    ``ws://127.0.0.1:8765`` (``DaemonConfig.kernel_serve_ws_url`` 默认
    loopback)与本字段无关。
    """

    host: str = "0.0.0.0"
    port: int = 8765
    health_path: str = "/health"

    @property
    def base_url(self) -> str:
        """HTTP base URL for kernel serve."""
        return f"http://{self.host}:{self.port}"

    @property
    def health_url(self) -> str:
        """Full health check URL."""
        return f"{self.base_url}{self.health_path}"


class LobeHubConfig(BaseModel):
    """LobeHub frontend (Next.js)."""

    host: str = "127.0.0.1"
    release: str = "v2.2.13"
    dir: str = "lobehub-ui"
    dev_port: int = 3010
    spa_port: int = 9876
    env_template: str = "deploy/lobehub/.env.lca"

    @property
    def dev_url(self) -> str:
        """Dev server URL."""
        return f"http://{self.host}:{self.dev_port}"

    @property
    def spa_url(self) -> str:
        """Vite SPA sidecar URL. Independent lifetime from :dev_port."""
        return f"http://{self.host}:{self.spa_port}"


class InfraConfig(BaseModel):
    """Docker-compose infrastructure (postgres, redis, s3)."""

    host: str = "127.0.0.1"
    compose_dir: str = "lobehub-ui/docker-compose/dev"
    services: list[str] = Field(
        default_factory=lambda: ["postgresql", "redis", "rustfs", "rustfs-init"]
    )
    ports: dict[str, int] = Field(default_factory=lambda: {"postgres": 25432, "redis": 6379})


class OnlyboxesConfig(BaseModel):
    """Onlyboxes terminalExec worker + LCA runtime image."""

    worker_service: str = "onlyboxes-worker-docker"
    terminal_image: str = "onlyboxes-terminal-local:lca"
    stale_image: str = "coolfan1024/onlyboxes-runtime:default"
    env_key: str = "WORKER_TERMINAL_EXEC_DOCKER_IMAGE"
    configure_script: str = "deploy/onlyboxes/configure-terminal-runtime.sh"
    build_script: str = "deploy/onlyboxes/build-terminal-image.sh"

    @property
    def dropin_path(self) -> Path:
        """systemd drop-in that actually loads (unit.service.d, not unit.d)."""
        return Path(
            f"/etc/systemd/system/{self.worker_service}.service.d/lca-terminal-runtime.conf"
        )

    @property
    def legacy_dropin_dir(self) -> Path:
        """Path older scripts wrote; systemd ignores it."""
        return Path(f"/etc/systemd/system/{self.worker_service}.d")

    @property
    def configure_cmd(self) -> str:
        return f"./{self.configure_script}"

    @property
    def build_and_configure_cmd(self) -> str:
        return f"./{self.build_script} && ./{self.configure_script}"


class DaemonConfig(BaseModel):
    """Agent CLI daemon (sandbox-user connect)."""

    kernel_serve_ws_url: str = ""  # empty = derive from kernel_serve config at runtime
    user: str = "sandbox-user"
    workspace: str = "/home/sandbox-user"
    host_config: str = "lca-host.yaml"

    def resolve_kernel_serve_url(self, host: str, port: int) -> str:
        """Resolve kernel serve WebSocket URL, defaulting to kernel_serve config."""
        if self.kernel_serve_ws_url:
            return self.kernel_serve_ws_url
        return f"ws://{host}:{port}"


class OpsConfig(BaseModel):
    """Root configuration. One object, one YAML, one source of truth.

    Load order: defaults → YAML file → environment variables.
    """

    kernel_serve: KernelServeConfig = Field(default_factory=KernelServeConfig)
    lobehub: LobeHubConfig = Field(default_factory=LobeHubConfig)
    infra: InfraConfig = Field(default_factory=InfraConfig)
    daemon: DaemonConfig = Field(default_factory=DaemonConfig)
    onlyboxes: OnlyboxesConfig = Field(default_factory=OnlyboxesConfig)
    run_dir: str = ".lca-ops"
    sudo_pass_file: str = ".lobehub-stack/sudo.pass"  # noqa: S105

    @classmethod
    def load(cls, path: Path | str | None = None) -> Self:
        """Load config: defaults ← YAML ← env overlay."""
        config_path = Path(path) if path else Path("lca-ops.yaml")

        if config_path.is_file():
            data = yaml.safe_load(config_path.read_text()) or {}
            instance = cls.model_validate(data)
        else:
            instance = cls()

        return instance._apply_environ()

    def _apply_environ(self) -> Self:
        """Overlay well-known environment variables.

        Adopts new ``LCA_KERNEL_SERVE_*`` env names (ADR-0119 followup-2).
        Old ``GATEWAY_*`` names still resolved with a deprecation warning so
        existing deployment scripts survive the transition window.
        """
        import structlog

        ks = self.kernel_serve
        if host := os.environ.get("LCA_KERNEL_SERVE_HOST"):
            ks = ks.model_copy(update={"host": host})
        elif host := os.environ.get("GATEWAY_HOST"):
            ks = ks.model_copy(update={"host": host})
            structlog.get_logger("lca.cli.config").warning(
                "env_var_deprecated",
                old="GATEWAY_HOST",
                new="LCA_KERNEL_SERVE_HOST",
            )
        if port := os.environ.get("LCA_KERNEL_SERVE_PORT"):
            ks = ks.model_copy(update={"port": int(port)})
        elif port := os.environ.get("GATEWAY_PORT"):
            ks = ks.model_copy(update={"port": int(port)})
            structlog.get_logger("lca.cli.config").warning(
                "env_var_deprecated",
                old="GATEWAY_PORT",
                new="LCA_KERNEL_SERVE_PORT",
            )
        if bind := os.environ.get("LCA_KERNEL_SERVE_BIND"):
            ks = ks.model_copy(update={"bind": bind})
        elif bind := os.environ.get("GATEWAY_BIND"):
            ks = ks.model_copy(update={"bind": bind})
            structlog.get_logger("lca.cli.config").warning(
                "env_var_deprecated",
                old="GATEWAY_BIND",
                new="LCA_KERNEL_SERVE_BIND",
            )

        lh = self.lobehub
        if host := os.environ.get("LOBE_HOST"):
            lh = lh.model_copy(update={"host": host})
        if release := os.environ.get("LOBEHUB_RELEASE"):
            lh = lh.model_copy(update={"release": release})
        if dev_port := os.environ.get("LOBE_DEV_PORT"):
            lh = lh.model_copy(update={"dev_port": int(dev_port)})

        ob = self.onlyboxes
        if image := os.environ.get("ONLYBOXES_TERMINAL_IMAGE"):
            ob = ob.model_copy(update={"terminal_image": image})
        if service := os.environ.get("ONLYBOXES_WORKER_SERVICE"):
            ob = ob.model_copy(update={"worker_service": service})

        return self.model_copy(update={"kernel_serve": ks, "lobehub": lh, "onlyboxes": ob})

    @property
    def root(self) -> Path:
        """Project root (where this config lives)."""
        return Path.cwd()

    @property
    def state_dir(self) -> Path:
        """Runtime state directory (pids, logs, stamps)."""
        return self.root / self.run_dir
