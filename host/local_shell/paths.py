"""Resolve tool paths against the configured workspace (guest root remapped)."""

from __future__ import annotations

from pathlib import Path

from host.paths import resolve_guest_path

MAX_READ_BYTES = 10 * 1024 * 1024
MAX_TEXT_CHARS = 200_000


def resolve_local(raw: str, workspace: Path, *, mount: str) -> Path:
    resolved = resolve_guest_path(raw or ".", workspace, mount=mount)
    root = workspace.resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return root / resolved.name
    return resolved


def truncate_text(text: str, limit: int = MAX_TEXT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...[truncated {len(text) - limit} chars]"
