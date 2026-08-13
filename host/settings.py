"""Host sidecar settings. Same LCA_HOST_* prefix as gateway Presence."""

from __future__ import annotations

import socket
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class HostSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LCA_HOST_", extra="ignore")

    token: str = "lca-local-host"  # noqa: S105 — stack-local shared secret, not a user password
    device_id: str = "local-host"
    name: str = ""
    gateway: str = "ws://127.0.0.1:8765/presence/connect"
    reconnect_s: float = 2.0
    shell: str = ""
    root: str = ""

    def display_name(self) -> str:
        return self.name.strip() or socket.gethostname()

    def workspace(self) -> Path:
        raw = self.root.strip()
        return Path(raw).expanduser() if raw else Path.home()

    def shell_argv(self) -> list[str]:
        import os

        shell = self.shell.strip() or os.environ.get("SHELL") or "/bin/bash"
        return [shell, "-i"]
