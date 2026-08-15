"""Host runtime configuration — Pydantic models + YAML SSOT.

Config file: ``lca-host.yaml`` (project root).  One file defines the
entire host environment: shared resources, per-user workspaces, tool
chains, and the device gateway connection.

Reading the YAML is reading the architecture.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from lca.contracts.models.core.preinstall import KEY_PYTHON_IMPORTS
from lca.contracts.models.core.sandbox import SANDBOX_OUTPUT_SUBDIR
from lca.layer0_infra.plane.paths import join_under

# ── leaf models ──────────────────────────────────────────────────────


class PathConfig(BaseModel):
    """System-level path layout."""

    tool_dir: str = "/usr/local/bin"
    cli_dir: str = "/opt/lca"
    venv_dir: str = "/opt/lca/venv"
    profile_d: str = "/etc/profile.d/lca.sh"
    etc_environment: str = "/etc/environment"
    managed_path: str = (
        "/opt/lca/venv/bin:/usr/local/bin:/usr/bin:/bin:/usr/local/sbin:/usr/sbin:/sbin"
    )


class GatewayConfig(BaseModel):
    """Device gateway connection."""

    url: str = "ws://127.0.0.1:8765"
    health_url: str = "http://127.0.0.1:8765/health"
    token: str = Field(default="lca-local-host")


class SystemPackagesConfig(BaseModel):
    """Packages to install via system package manager (idempotent)."""

    apt: list[str] = Field(
        default_factory=lambda: [
            "pandoc",
            "ffmpeg",
            "jq",
            "poppler-utils",
            "fonts-wqy-zenhei",
            "fonts-noto-cjk-extra",
        ]
    )
    dnf: list[str] = Field(
        default_factory=lambda: [
            "pandoc",
            "ffmpeg",
            "jq",
            "poppler-utils",
            "wqy-microhei-fonts",
        ]
    )
    yum: list[str] = Field(
        default_factory=lambda: [
            "pandoc",
            "ffmpeg",
            "jq",
            "poppler-utils",
            "wqy-microhei-fonts",
        ]
    )


class ToolsConfig(BaseModel):
    """Binaries to copy into tool_dir so sandbox users can find them."""

    names: list[str] = Field(default_factory=lambda: ["python3", "uv", "officecli"])
    python_min_version: str = "3.10"
    python_candidates: list[str] = Field(
        default_factory=lambda: ["/usr/local/bin/python3.12", "/usr/bin/python3.12"]
    )


class VenvConfig(BaseModel):
    """Shared Python venv."""

    requirements_file: str = "deploy/onlyboxes/requirements-python.txt"
    python_index: str = "https://pypi.tuna.tsinghua.edu.cn/simple"
    check_imports: list[str] = Field(default_factory=lambda: list(KEY_PYTHON_IMPORTS))


class CLIConfig(BaseModel):
    """LCA CLI (lca-cli) deployment."""

    source_dir: str = "packages/lca-cli"
    gateway_client_dir: str = "packages/gateway-client"


# ── user model ────────────────────────────────────────────────────────


class UserConfig(BaseModel):
    """One execution user — the unit of provisioning."""

    name: str
    home: str = ""
    outputs_subdir: str = SANDBOX_OUTPUT_SUBDIR
    state_subdir: str = ".lca"
    shell: str = "/bin/bash"

    def model_post_init(self, __context: Any) -> None:
        if not self.home:
            self.home = f"/home/{self.name}"

    @property
    def outputs_dir(self) -> str:
        return join_under(self.home, self.outputs_subdir)

    @property
    def state_dir(self) -> str:
        return join_under(self.home, self.state_subdir)


# ── root config ───────────────────────────────────────────────────────


class HostRuntimeConfig(BaseModel):
    """Top-level config — one object, one YAML, one source of truth."""

    paths: PathConfig = Field(default_factory=PathConfig)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    system_packages: SystemPackagesConfig = Field(default_factory=SystemPackagesConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    venv: VenvConfig = Field(default_factory=VenvConfig)
    cli: CLIConfig = Field(default_factory=CLIConfig)
    users: list[UserConfig] = Field(default_factory=list)

    @classmethod
    def from_yaml(cls, path: str | Path) -> HostRuntimeConfig:
        text = Path(path).read_text(encoding="utf-8")
        data = yaml.safe_load(text) or {}
        return cls.model_validate(data)

    @classmethod
    def from_yaml_or_default(cls, path: str | Path = "lca-host.yaml") -> HostRuntimeConfig:
        p = Path(path)
        if p.is_file():
            return cls.from_yaml(p)
        return cls()

    def to_yaml(self, path: str | Path) -> None:
        Path(path).write_text(
            yaml.dump(
                self.model_dump(mode="json"),
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )

    def find_user(self, name: str) -> UserConfig | None:
        for user in self.users:
            if user.name == name:
                return user
        return None


# ── default YAML template ─────────────────────────────────────────────

DEFAULT_YAML = """\
# lca-host.yaml — LCA Host Runtime Configuration (SSOT)
#
# This file is the single source of truth for the host environment.
# Edit this file, then run:  ./scripts/lca-ops provision
#
# Architecture:
#   - Shared layer: system packages, tools, venv, CLI → shared across users
#   - User layer:   each user gets an account + workspace + daemon
#
# See lca/layer0_infra/host_runtime/config.py for the Pydantic models.

paths:
  tool_dir: /usr/local/bin
  cli_dir: /opt/lca
  venv_dir: /opt/lca/venv
  managed_path: "/opt/lca/venv/bin:/usr/local/bin:/usr/bin:/bin:/usr/local/sbin:/usr/sbin:/sbin"

gateway:
  url: "ws://127.0.0.1:8765"
  token: lca-local-host

system_packages:
  dnf: [pandoc, ffmpeg, jq, poppler-utils, wqy-microhei-fonts]

tools:
  names: [python3, uv, officecli]
  python_min_version: "3.10"
  python_candidates: [/usr/local/bin/python3.12, /usr/bin/python3.12]

venv:
  requirements_file: deploy/onlyboxes/requirements-python.txt
  python_index: "https://pypi.tuna.tsinghua.edu.cn/simple"
  check_imports: [pandas, numpy, matplotlib, openpyxl, reportlab, requests]

cli:
  source_dir: packages/lca-cli
  gateway_client_dir: packages/gateway-client

# ── Users ──────────────────────────────────────────────────────────
# Each user gets: system account, home dir, outputs/, .lca/ state, daemon
# Add more users and re-run: ./scripts/lca-ops provision
users:
  - name: sandbox-user
    home: /home/sandbox-user
"""
