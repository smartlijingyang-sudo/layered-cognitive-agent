"""Prompt text for the primary product environment."""

from __future__ import annotations

from lca.contracts.models.core.plane import PlaneKind, PlaneRef
from lca.infrastructure.file_store import FileStore
from lca.infrastructure.runtime_plane.resolve import (
    make_sandbox_ref,
    resolve_plane_bindings,
    sandbox_ref_from,
)
from lca.infrastructure.runtime_plane.scope import current_primary
from lca.infrastructure.sandbox.factory import resolve_sandbox


def current_primary_ref() -> PlaneRef | None:
    primary = current_primary()
    if primary is not None:
        return primary
    sandbox = resolve_sandbox()
    sandbox_ref = sandbox_ref_from(sandbox) if sandbox is not None else None
    return resolve_plane_bindings(None, sandbox_ref).primary


def environment_note() -> str:
    primary = current_primary_ref()
    if primary is not None:
        return plane_system_role(primary)
    return plane_system_role(make_sandbox_ref())


def skill_preamble(store: FileStore | None = None) -> str:
    """Deliverable hint plus staged attachment paths (same SSOT as system role)."""
    from lca.infrastructure.attachment.prompt import format_skill_attachment_block

    lines = ["当前工作目录是工作根。交付物写相对路径 outputs/。"]
    attachment_block = format_skill_attachment_block(store)
    if attachment_block:
        lines.append(attachment_block)
    return "\n".join(lines) + "\n"


def plane_system_role(plane: PlaneRef) -> str:
    if plane.kind is PlaneKind.MACHINE:
        from lca.infrastructure.observability.facade.run_ambit import current_file_store as get_current_run_file_store
        from lca.infrastructure.attachment.system_role_renderer import render_system_role
        from lca.infrastructure.runtime_plane.preinstall_prompt import (
            render_preinstalled_block,
        )

        result = render_system_role(
            plane,
            template_name="machine_system_role",
            store=get_current_run_file_store(),
            extra_placeholders={
                "{{preinstalled}}": render_preinstalled_block(plane=PlaneKind.MACHINE),
            },
        )
        rendered = result.text
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
