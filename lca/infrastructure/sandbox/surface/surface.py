"""Prompt text for the primary product environment."""

from __future__ import annotations

from lca.contracts.models.core.state.plane import PlaneRef
from lca.infrastructure.file.store import FileStore
from lca.infrastructure.runtime_plane.resolve.resolve import (
    resolve_plane_bindings,
    sandbox_ref_from,
)
from lca.infrastructure.runtime_plane.scope.scope import current_primary
from lca.infrastructure.sandbox.factory.factory import resolve_sandbox


def current_primary_ref() -> PlaneRef | None:
    primary = current_primary()
    if primary is not None:
        return primary
    sandbox = resolve_sandbox()
    sandbox_ref = sandbox_ref_from(sandbox) if sandbox is not None else None
    return resolve_plane_bindings(None, sandbox_ref).primary


def environment_note() -> str:
    """Render the current plane's system-role text.

    Delegates to the execution-plane prompt assembler so there is a single
    rendering pipeline for sandbox and machine planes.
    """
    from lca.infrastructure.runtime_plane.prompt.assembler import render_plane_role

    return render_plane_role()


def skill_preamble(store: FileStore | None = None) -> str:
    """Deliverable hint plus staged attachment paths (same SSOT as system role)."""
    from lca.infrastructure.attachment.prompt.prompt import format_skill_attachment_block

    lines = ["当前工作目录是工作根。交付物写相对路径 outputs/。"]
    attachment_block = format_skill_attachment_block(store)
    if attachment_block:
        lines.append(attachment_block)
    return "\n".join(lines) + "\n"


__all__ = ["current_primary_ref", "environment_note", "skill_preamble"]
