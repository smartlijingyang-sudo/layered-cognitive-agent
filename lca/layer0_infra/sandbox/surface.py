"""Which computer the agent is on. Agent still sees /mnt/data either way."""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.models.core.sandbox import SANDBOX_MOUNT_ROOT

BACKEND_HOST = "host"
BACKEND_ONLYBOXES = "onlyboxes"


@dataclass(frozen=True, slots=True)
class ExecutionSurface:
    backend: str
    guest_root: str = SANDBOX_MOUNT_ROOT

    @property
    def outputs_dir(self) -> str:
        return f"{self.guest_root.rstrip('/')}/outputs"


def current_surface() -> ExecutionSurface:
    from lca.layer0_infra.sandbox.factory import resolve_sandbox

    bound = resolve_sandbox()
    name = getattr(bound, "name", "") or BACKEND_ONLYBOXES
    if name == BACKEND_HOST:
        from lca.layer0_infra.sandbox.host_settings import load_host_settings

        return ExecutionSurface(BACKEND_HOST, guest_root=load_host_settings().guest_mount())
    return ExecutionSurface(BACKEND_ONLYBOXES)


def environment_note(surface: ExecutionSurface) -> str:
    root = surface.guest_root
    outputs = surface.outputs_dir
    if surface.backend == BACKEND_HOST:
        return (
            "**Important:** Tools run on the connected host computer. "
            f"The workspace you use is still `{root}` (runtime maps it to the configured host directory). "
            f"Do not switch to `$HOME` or `/mnt` on the real disk — stay under `{root}`.\n"
            f"- Each run mounts attachments at `{root}/<filename>`\n"
            f"- Write deliverables under `{outputs}`\n"
            "- Prefer preinstalled officecli and Python libraries; if a command is missing, report it — do not curl-install"
        )
    return (
        "**Important:** This is a CLOUD SANDBOX environment, NOT the user's local file system.\n"
        "- Files created here are temporary and session-specific\n"
        "- Each run has its own isolated workspace\n"
        '- Default shell is /bin/sh (not bash). For bash-specific features use: bash -c "your_command"\n'
        "- Commands time out after 120 seconds unless a longer timeout is set\n"
        f"- Workspace root: {root}\n"
        f"- **Output directory (required for generated files): {outputs}**"
    )


def skill_preamble(surface: ExecutionSurface) -> str:
    root = surface.guest_root
    outputs = surface.outputs_dir
    if surface.backend == BACKEND_HOST:
        return (
            f"执行面：本机 host。officecli 与常用 Python 库应已在 PATH/当前解释器中。\n"
            f"工作区对你仍是 `{root}`；交付物写 `{outputs}`。不要改用家目录或 /mnt。\n"
            "officecli 不在 PATH 时报告本机缺命令，勿 curl / pip 现场安装。\n"
        )
    return (
        f"执行面：Onlyboxes 沙箱。officecli 预装在 terminal 镜像内。\n"
        f"工作区 `{root}`；交付物写 `{outputs}`。不要在宿主安装软件。\n"
    )
