"""Resolve paths on the host workspace. No guest-root translation."""

from __future__ import annotations

from pathlib import Path


def resolve_host_path(raw: str, workspace: Path) -> Path:
    text = (raw or "").strip() or "."
    path = Path(text).expanduser()
    if path.is_absolute():
        return path
    return (workspace / path).resolve()


def resolve_guest_path(raw: str, workspace: Path, *, mount: str = "") -> Path:
    """Compatibility alias. Does not remap mount prefixes."""
    del mount
    return resolve_host_path(raw, workspace)
