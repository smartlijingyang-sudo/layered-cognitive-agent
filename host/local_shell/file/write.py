"""Port of packages/local-file-shell/src/file/write.ts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from host.local_shell.file.bind import resolve_bound


def write_local_file(payload: dict[str, Any], workspace: Path, *, mount: str) -> dict[str, Any]:
    raw = str(payload.get("path") or "")
    if not raw:
        return {"success": False, "error": "Path cannot be empty"}
    if "content" not in payload:
        return {"success": False, "error": "Content cannot be empty"}
    file_path = resolve_bound(raw, workspace, mount=mount, cwd=payload.get("cwd"))
    try:
        dest = Path(file_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(str(payload.get("content") or ""), encoding="utf-8")
        return {"success": True, "content": f"wrote {dest.name}"}
    except OSError as exc:
        return {"success": False, "error": f"Failed to write file: {exc}"}
