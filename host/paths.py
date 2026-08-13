"""Guest /mnt/data ↔ configured host workspace. Agent never sees the host path."""

from __future__ import annotations

import re
from pathlib import Path

from lca.contracts.models.core.sandbox import SANDBOX_MOUNT_ROOT


def guest_root(raw: str | None = None) -> str:
    text = (raw or SANDBOX_MOUNT_ROOT).strip() or SANDBOX_MOUNT_ROOT
    return text.rstrip("/") or SANDBOX_MOUNT_ROOT


def resolve_guest_path(raw: str, workspace: Path, *, mount: str = SANDBOX_MOUNT_ROOT) -> Path:
    text = raw.strip() or "."
    root = guest_root(mount)
    if text == root or text.startswith(f"{root}/"):
        rest = text[len(root) :].lstrip("/")
        return (workspace / rest).resolve()
    path = Path(text).expanduser()
    if path.is_absolute():
        return path
    return (workspace / path).resolve()


def rewrite_guest_refs(text: str, workspace: Path, *, mount: str = SANDBOX_MOUNT_ROOT) -> str:
    """Rewrite guest-root prefixes in commands/scripts to the host workspace."""
    root = guest_root(mount)
    host = workspace.resolve().as_posix()
    if root == host:
        return text
    pattern = re.compile(rf"(?<![\w./]){re.escape(root)}(?=/|\"|'|\s|$)")
    return pattern.sub(host, text)
