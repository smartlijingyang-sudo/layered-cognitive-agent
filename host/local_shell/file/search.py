"""Port of packages/local-file-shell/src/file/search.ts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from host.local_shell.file.bind import resolve_bound


def search_local_files(payload: dict[str, Any], workspace: Path, *, mount: str) -> dict[str, Any]:
    keywords = str(payload.get("keywords") or payload.get("keyword") or "")
    scope = payload.get("onlyIn") or payload.get("directory") or payload.get("cwd") or "."
    content_contains = payload.get("contentContains")
    limit = int(payload.get("limit") or 30)
    suffix = str(payload.get("file_type") or payload.get("fileTypes") or "")
    if isinstance(payload.get("fileTypes"), list) and payload["fileTypes"]:
        suffix = str(payload["fileTypes"][0])
    base = Path(resolve_bound(str(scope), workspace, mount=mount))
    wants_hidden = keywords.startswith(".")
    found: list[dict[str, Any]] = []
    needle = keywords.lower()
    for path in base.rglob("*"):
        if not path.is_file() or "node_modules" in path.parts or ".git" in path.parts:
            continue
        if not wants_hidden and any(part.startswith(".") for part in path.relative_to(base).parts):
            continue
        if needle and needle not in path.name.lower():
            continue
        if suffix and path.suffix.lower().lstrip(".") != suffix.lower().lstrip("."):
            continue
        if content_contains:
            try:
                if str(content_contains) not in path.read_text(encoding="utf-8", errors="replace"):
                    continue
            except OSError:
                continue
        found.append({"name": path.name, "path": str(path)})
        if len(found) >= limit:
            break
    return {"success": True, "files": found, "content": str(len(found))}
