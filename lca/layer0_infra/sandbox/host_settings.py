"""Host runtime profile — SSOT for operator, workspace, guest path.

Env prefix ``LCA_HOST_``. Empty ``root`` means ``/home/{user}``.
Guest path defaults to the sandbox contract (``SANDBOX_MOUNT_ROOT``).
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from lca.contracts.models.core.sandbox import SANDBOX_MOUNT_ROOT, SANDBOX_OUTPUT_SUBDIR


class HostRuntimeSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LCA_HOST_",
        env_file=(".env", "deploy/lobehub/.env.lca"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    user: str = "sandbox-user"
    root: str = ""
    guest_root: str = SANDBOX_MOUNT_ROOT
    token: str = "lca-local-host"  # noqa: S105
    device_id: str = "local-host"
    name: str = ""
    gateway: str = "ws://127.0.0.1:8765/presence/connect"
    reconnect_s: float = 2.0
    shell: str = ""

    def operator(self) -> str:
        name = self.user.strip()
        return name or "sandbox-user"

    def display_name(self) -> str:
        import socket

        return self.name.strip() or socket.gethostname()

    def guest_mount(self) -> str:
        text = self.guest_root.strip() or SANDBOX_MOUNT_ROOT
        return text.rstrip("/") or SANDBOX_MOUNT_ROOT

    def workspace(self) -> Path:
        raw = self.root.strip()
        if raw:
            return Path(raw).expanduser()
        return Path("/home") / self.operator()

    def outputs_dir(self) -> Path:
        return self.workspace() / SANDBOX_OUTPUT_SUBDIR

    def shell_argv(self) -> list[str]:
        import os

        shell = self.shell.strip() or os.environ.get("SHELL") or "/bin/bash"
        return [shell, "-i"]

    def as_shell(self) -> str:
        """KEY=value lines for bash eval. Scripts must not hardcode paths."""
        ws = self.workspace()
        lines = (
            f"LCA_HOST_USER={_sh(self.operator())}",
            f"LCA_HOST_ROOT={_sh(str(ws))}",
            f"LCA_HOST_GUEST_ROOT={_sh(self.guest_mount())}",
            f"LCA_HOST_OUTPUTS={_sh(str(self.outputs_dir()))}",
        )
        return "\n".join(lines) + "\n"


def _sh(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def load_host_settings() -> HostRuntimeSettings:
    return HostRuntimeSettings()


if __name__ == "__main__":
    import sys

    sys.stdout.write(load_host_settings().as_shell())
