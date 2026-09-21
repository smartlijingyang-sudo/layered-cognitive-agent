"""Prompt text for the primary product environment."""

from __future__ import annotations

from lca.infrastructure.file.store import FileStore
from lca.infrastructure.runtime_plane.prompt.assembler import render_plane_role


def environment_note() -> str:
    """Render the current plane's system-role text.

    Delegates to the execution-plane prompt assembler so there is a single
    rendering pipeline for sandbox and machine planes.
    """
    return render_plane_role()


def skill_preamble(store: FileStore | None = None) -> str:
    """Deliverable hint plus staged attachment paths (same SSOT as system role)."""
    from lca.infrastructure.attachment.prompt.prompt import format_skill_attachment_block

    lines = ["当前工作目录是工作根。交付物写相对路径 outputs/。"]
    attachment_block = format_skill_attachment_block(store)
    if attachment_block:
        lines.append(attachment_block)
    return "\n".join(lines) + "\n"


__all__ = ["environment_note", "skill_preamble"]
