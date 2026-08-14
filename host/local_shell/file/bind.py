"""Bind official path resolution to the host workspace (guest root overlay)."""

from __future__ import annotations

from pathlib import Path

from host.local_shell.file.expand_tilde import resolve_against_cwd


def resolve_bound(
    raw: str | None,
    workspace: Path,
    *,
    mount: str,
    cwd: str | None = None,
) -> str:
    """Resolve against cwd. Absolute paths stay absolute. No guest remap."""
    del mount
    text = raw or "."
    bound = cwd or str(workspace)
    resolved = resolve_against_cwd(text, bound, home=workspace) or text
    return str(Path(resolved).expanduser())
