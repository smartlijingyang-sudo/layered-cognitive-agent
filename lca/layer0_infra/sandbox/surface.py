"""Prompt text for the primary product environment."""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.models.core.plane import PlaneKind, PlaneRef
from lca.contracts.models.core.sandbox import SANDBOX_MOUNT_ROOT
from lca.layer0_infra.plane.machine import resolve_machine
from lca.layer0_infra.plane.resolve import resolve_plane_bindings, sandbox_ref_from
from lca.layer0_infra.plane.scope import current_primary
from lca.layer0_infra.sandbox.factory import resolve_sandbox

BACKEND_HOST = "host"
BACKEND_ONLYBOXES = "onlyboxes"


@dataclass(frozen=True, slots=True)
class ExecutionSurface:
    """Deprecated prompt adapter. Disk identity is PlaneRef."""

    backend: str
    guest_root: str = SANDBOX_MOUNT_ROOT

    @property
    def outputs_dir(self) -> str:
        return f"{self.guest_root.rstrip('/')}/outputs"


def current_primary_ref() -> PlaneRef | None:
    primary = current_primary()
    if primary is not None:
        return primary
    sandbox = resolve_sandbox()
    sandbox_ref = sandbox_ref_from(sandbox) if sandbox is not None else None
    return resolve_plane_bindings(resolve_machine(), sandbox_ref).primary


def current_surface() -> ExecutionSurface:
    primary = current_primary_ref()
    if primary is not None and primary.kind is PlaneKind.MACHINE:
        return ExecutionSurface(BACKEND_HOST, guest_root=primary.root)
    return ExecutionSurface(BACKEND_ONLYBOXES)


def environment_note(surface: ExecutionSurface | None = None) -> str:
    primary = current_primary_ref()
    if primary is not None:
        return plane_system_role(primary)
    if surface is not None and surface.backend == BACKEND_HOST:
        return plane_system_role(
            PlaneRef(
                id="host",
                label="host",
                kind=PlaneKind.MACHINE,
                root=surface.guest_root,
                outputs_dir=surface.outputs_dir,
            )
        )
    return _sandbox_note(SANDBOX_MOUNT_ROOT, f"{SANDBOX_MOUNT_ROOT}/outputs")


def skill_preamble(surface: ExecutionSurface | None = None) -> str:
    del surface
    primary = current_primary_ref()
    if primary is not None and primary.kind is PlaneKind.MACHINE:
        return (
            f"执行面：用户的机器 {primary.label}。\n"
            f"工作根 `{primary.root}`；交付物写 `{primary.outputs_dir}`。\n"
            "路径按该 OS 原样使用，不要改写成 /mnt/data。\n"
        )
    return (
        "执行面：Onlyboxes 沙箱。officecli 预装在 terminal 镜像内。\n"
        f"工作区 `{SANDBOX_MOUNT_ROOT}`；交付物写 `{SANDBOX_MOUNT_ROOT}/outputs`。不要在宿主安装软件。\n"
    )


def plane_system_role(plane: PlaneRef) -> str:
    if plane.kind is PlaneKind.MACHINE:
        from lca.layer0_infra.plane.prompts import load_plane_prompt

        template = load_plane_prompt("machine_system_role")
        rendered = (
            template.replace("{{label}}", plane.label)
            .replace("{{platform}}", plane.platform or "unknown")
            .replace("{{root}}", plane.root)
            .replace("{{outputs_dir}}", plane.outputs_dir)
        )
        if plane.home:
            rendered += (
                f"\n- User home (for spoken locations like Desktop only): `{plane.home}`"
            )
        return rendered
    return _sandbox_note(plane.root, plane.outputs_dir)


def _sandbox_note(root: str, outputs: str) -> str:
    return (
        "**Important:** This is a CLOUD SANDBOX environment, NOT the user's local file system.\n"
        "- Files created here are temporary and session-specific\n"
        "- Each run has its own isolated workspace\n"
        '- Default shell is /bin/sh (not bash). For bash-specific features use: bash -c "your_command"\n'
        "- Commands time out after 120 seconds unless a longer timeout is set\n"
        f"- Workspace root: {root}\n"
        f"- **Output directory (required for generated files): {outputs}**"
    )
