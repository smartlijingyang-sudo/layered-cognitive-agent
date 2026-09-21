"""Dedicated configuration loader for external MCP servers.

Supports loading from:
1. Environment variable ``LCA_MCP_CONFIG`` (explicit path)
2. Project-level ``./mcp.yaml`` or ``./.lca/mcp.yaml``
3. User-level ``~/.lca/mcp.yaml``
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import structlog
import yaml
from pydantic import BaseModel, Field

from lca.contracts.models.mcp.types import MCPServerConfig

_log = structlog.get_logger(__name__)

# Regex for environment variable substitution: ${VAR} or ${VAR:-default}
_ENV_VAR_PATTERN = re.compile(r"\$\{(\w+)(?::-(.*?))?\}")


def _interpolate_env_vars(text: str) -> str:
    """Replace ${VAR_NAME} or ${VAR_NAME:-default} with OS environment values."""

    def _replace(match: re.Match[str]) -> str:
        var_name = match.group(1)
        default_val = match.group(2) if match.group(2) is not None else ""
        return os.environ.get(var_name, default_val)

    return _ENV_VAR_PATTERN.sub(_replace, text)


class MCPConfigFile(BaseModel):
    """Schema for mcp.yaml configuration file."""

    servers: dict[str, MCPServerConfig] = Field(default_factory=dict)


def find_mcp_config_path() -> Path | None:
    """Locate dedicated mcp.yaml in project or user directories.

    Priority order:
    1. Explicit environment variable ``LCA_MCP_CONFIG``
    2. Project SSOT: ``<project_root>/.lca/mcp.yaml`` or ``.lca/config/mcp.yaml``
    3. User Global SSOT: ``~/.lca/mcp.yaml`` or ``~/.lca/config/mcp.yaml``
    4. Project root fallbacks: ``mcp.yaml``, ``mcp-servers.yaml``, ``.mcp.json``
    5. User home fallback: ``~/.mcp.json``
    """
    # 1. Explicit env var
    env_path = os.environ.get("LCA_MCP_CONFIG")
    if env_path:
        p = Path(env_path).expanduser().resolve()
        if p.is_file():
            return p

    # 2. Project SSOT (.lca/ directory)
    cwd = Path.cwd()
    project_ssot_candidates = [
        cwd / ".lca" / "mcp.yaml",
        cwd / ".lca" / "config" / "mcp.yaml",
    ]
    for c in project_ssot_candidates:
        if c.is_file():
            return c.resolve()

    # 3. User Global SSOT (~/.lca/ directory)
    user_ssot_candidates = [
        Path.home() / ".lca" / "mcp.yaml",
        Path.home() / ".lca" / "config" / "mcp.yaml",
    ]
    for c in user_ssot_candidates:
        if c.is_file():
            return c.resolve()

    # 4. Fallback legacy candidates in project root
    fallback_candidates = [
        cwd / "mcp.yaml",
        cwd / "mcp-servers.yaml",
        cwd / ".mcp.json",
        Path.home() / ".mcp.json",
    ]
    for c in fallback_candidates:
        if c.is_file():
            return c.resolve()

    return None


def load_mcp_servers(config_path: str | Path | None = None) -> dict[str, MCPServerConfig]:
    """Parse and validate dedicated MCP configuration file."""
    path = Path(config_path).expanduser().resolve() if config_path else find_mcp_config_path()
    if path is None or not path.is_file():
        _log.debug("no_mcp_config_found")
        return {}

    try:
        raw_text = path.read_text(encoding="utf-8")
        interpolated = _interpolate_env_vars(raw_text)
        data: dict[str, Any] = yaml.safe_load(interpolated) or {}

        # Support both `{servers: {...}}` and `{mcp_servers: {...}}` or top-level dictionary
        raw_servers: dict[str, Any] = {}
        if "servers" in data and isinstance(data["servers"], dict):
            raw_servers = data["servers"]
        elif "mcp_servers" in data and isinstance(data["mcp_servers"], dict):
            raw_servers = data["mcp_servers"]
        elif isinstance(data, dict):
            raw_servers = data

        configs: dict[str, MCPServerConfig] = {}
        for server_name, server_data in raw_servers.items():
            if not isinstance(server_data, dict):
                continue
            if "name" not in server_data:
                server_data["name"] = server_name
            cfg = MCPServerConfig.model_validate(server_data)
            if cfg.enabled:
                configs[server_name] = cfg

        _log.info("mcp_config_loaded", path=str(path), servers_count=len(configs))
        return configs

    except Exception as e:
        _log.error("mcp_config_load_failed", path=str(path), error=str(e))
        raise ValueError(f"Failed to load MCP configuration from {path}: {e}") from e
