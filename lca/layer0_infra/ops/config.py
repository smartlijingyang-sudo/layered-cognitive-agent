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


class GatewayConfig(BaseModel):
    """LCA API gateway (Starlette)."""

    host: str = "127.0.0.1"
    port: int = 8765
    bind: str = "0.0.0.0"  # noqa: S104
    health_path: str = "/health"
    entry: list[str] = Field(
        default_factory=lambda: ["uv", "run", "python", "scripts/serve_observability.py"]
    )
    watch: list[str] = Field(default_factory=lambda: ["gateway", "lca"])

    @property
    def base_url(self) -> str:
        """HTTP base URL for this gateway."""
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
    env_template: str = "deploy/lobehub/.env.lca"

    @property
    def dev_url(self) -> str:
        """Dev server URL."""
        return f"http://{self.host}:{self.dev_port}"


class InfraConfig(BaseModel):
    """Docker-compose infrastructure (postgres, redis, s3)."""

    host: str = "127.0.0.1"
    compose_dir: str = "lobehub-ui/docker-compose/dev"
    services: list[str] = Field(
        default_factory=lambda: ["postgresql", "redis", "rustfs", "rustfs-init"]
    )
    ports: dict[str, int] = Field(default_factory=lambda: {"postgres": 25432, "redis": 6379})


class DaemonConfig(BaseModel):
    """Agent CLI daemon (sandbox-user connect)."""

    gateway_ws_url: str = ""  # empty = derive from gateway config at runtime
    user: str = "sandbox-user"
    workspace: str = "/home/sandbox-user"
    host_config: str = "lca-host.yaml"

    def resolve_gateway_url(self, gateway_host: str, gateway_port: int) -> str:
        """Resolve gateway WebSocket URL, defaulting to gateway config."""
        if self.gateway_ws_url:
            return self.gateway_ws_url
        return f"ws://{gateway_host}:{gateway_port}"


class OpsConfig(BaseModel):
    """Root configuration. One object, one YAML, one source of truth.

    Load order: defaults → YAML file → environment variables.
    """

    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    lobehub: LobeHubConfig = Field(default_factory=LobeHubConfig)
    infra: InfraConfig = Field(default_factory=InfraConfig)
    daemon: DaemonConfig = Field(default_factory=DaemonConfig)
    run_dir: str = ".lca-ops"
    sudo_pass_file: str = ".lobehub-stack/sudo.pass"

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
        """Overlay well-known environment variables."""
        gw = self.gateway
        if host := os.environ.get("GATEWAY_HOST"):
            gw = gw.model_copy(update={"host": host})
        if port := os.environ.get("GATEWAY_PORT"):
            gw = gw.model_copy(update={"port": int(port)})
        if bind := os.environ.get("GATEWAY_BIND"):
            gw = gw.model_copy(update={"bind": bind})

        lh = self.lobehub
        if host := os.environ.get("LOBE_HOST"):
            lh = lh.model_copy(update={"host": host})
        if release := os.environ.get("LOBEHUB_RELEASE"):
            lh = lh.model_copy(update={"release": release})
        if dev_port := os.environ.get("LOBE_DEV_PORT"):
            lh = lh.model_copy(update={"dev_port": int(dev_port)})

        return self.model_copy(update={"gateway": gw, "lobehub": lh})

    @property
    def root(self) -> Path:
        """Project root (where this config lives)."""
        return Path.cwd()

    @property
    def state_dir(self) -> Path:
        """Runtime state directory (pids, logs, stamps)."""
        return self.root / self.run_dir
