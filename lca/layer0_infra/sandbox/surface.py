"""Prompt text for the primary product environment."""

from __future__ import annotations

from lca.contracts.models.core.plane import PlaneKind, PlaneRef
from lca.layer0_infra.plane.machine import resolve_machine
from lca.layer0_infra.plane.resolve import (
    make_sandbox_ref,
    resolve_plane_bindings,
    sandbox_ref_from,
)
from lca.layer0_infra.plane.scope import current_primary
from lca.layer0_infra.sandbox.factory import resolve_sandbox


def current_primary_ref() -> PlaneRef | None:
    primary = current_primary()
    if primary is not None:
        return primary
    sandbox = resolve_sandbox()
    sandbox_ref = sandbox_ref_from(sandbox) if sandbox is not None else None
    return resolve_plane_bindings(resolve_machine(), sandbox_ref).primary


def environment_note() -> str:
    primary = current_primary_ref()
    if primary is not None:
        return plane_system_role(primary)
    return plane_system_role(make_sandbox_ref())


def skill_preamble() -> str:
    """Path-agnostic reminder. Absolute roots live only in the system role."""
    return "当前工作目录是工作根。交付物写相对路径 outputs/。\n"


def plane_system_role(plane: PlaneRef) -> str:
    if plane.kind is PlaneKind.MACHINE:
        from lca.contracts.models.core.preinstall import render_preinstalled_block
        from lca.layer0_infra.plane.prompts import load_plane_prompt

        template = load_plane_prompt("machine_system_role")
        rendered = (
            template.replace("{{label}}", plane.label)
            .replace("{{platform}}", plane.platform or "unknown")
            .replace("{{root}}", plane.root)
            .replace("{{outputs_dir}}", plane.outputs_dir)
            .replace("{{preinstalled}}", render_preinstalled_block(plane=PlaneKind.MACHINE))
        )
        if plane.home:
            rendered += f"\n- User home (for spoken locations like Desktop only): `{plane.home}`"
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
