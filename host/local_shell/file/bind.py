"""Bind official path resolution to the host workspace (guest root overlay)."""

from __future__ import annotations

from pathlib import Path

from host.local_shell.file.expand_tilde import resolve_against_cwd
from host.paths import guest_root as normalize_guest


def resolve_bound(
    raw: str | None,
    workspace: Path,
    *,
    mount: str,
    cwd: str | None = None,
) -> str:
    """Official resolveAgainstCwd, then map guest-root onto the workspace."""
    root = normalize_guest(mount)
    text = raw or "."
    if text == root or text.startswith(f"{root}/"):
        rest = text[len(root) :].lstrip("/")
        text = str(workspace / rest)
    bound = cwd or str(workspace)
    resolved = resolve_against_cwd(text, bound, home=workspace) or text
    path = Path(resolved).resolve()
    root_path = workspace.resolve()
    try:
        path.relative_to(root_path)
        return str(path)
    except ValueError:
        return str(root_path / path.name)
