"""Port of packages/local-file-shell/src/file/glob.ts (pathlib instead of fast-glob)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from host.local_shell.file.bind import resolve_bound
from host.local_shell.file.has_hidden import has_hidden_segment


def glob_local_files(payload: dict[str, Any], workspace: Path, *, mount: str) -> dict[str, Any]:
    pattern = str(payload.get("pattern") or "*")
    scope = payload.get("scope") or payload.get("cwd") or payload.get("directory") or "."
    base = Path(resolve_bound(str(scope), workspace, mount=mount))
    wants_hidden = has_hidden_segment(pattern)
    try:
        matches = [
            str(p.relative_to(base)) if p.is_relative_to(base) else str(p)
            for p in base.rglob(pattern)
            if p.is_file()
            and "node_modules" not in p.parts
            and ".git" not in p.parts
            and (
                wants_hidden or not any(part.startswith(".") for part in p.relative_to(base).parts)
            )
        ]
        result: dict[str, Any] = {
            "success": True,
            "engine": "pathlib",
            "files": matches,
            "total_files": len(matches),
            "content": str(len(matches)),
        }
        if wants_hidden:
            result["hint"] = (
                "Auto-enabled hidden-file matching because pattern contains a dot-prefixed segment."
            )
        return result
    except OSError as exc:
        return {
            "success": False,
            "engine": "pathlib",
            "error": str(exc),
            "files": [],
            "total_files": 0,
        }
