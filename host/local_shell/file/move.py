"""Port of packages/local-file-shell/src/file/move.ts."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from host.local_shell.file.bind import resolve_bound


def move_local_files(payload: dict[str, Any], workspace: Path, *, mount: str) -> dict[str, Any]:
    items = payload.get("items") or payload.get("operations") or []
    results: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        old = str(item.get("oldPath") or item.get("source") or "")
        new = str(item.get("newPath") or item.get("destination") or "")
        source = resolve_bound(old, workspace, mount=mount, cwd=payload.get("cwd"))
        dest = resolve_bound(new, workspace, mount=mount, cwd=payload.get("cwd"))
        row: dict[str, Any] = {"sourcePath": source, "success": False}
        if not old or not new:
            row["error"] = "Both oldPath and newPath are required for each item."
            results.append(row)
            continue
        if os.path.normpath(source) == os.path.normpath(dest):
            row["success"] = True
            row["newPath"] = dest
            results.append(row)
            continue
        try:
            if not Path(source).exists():
                raise FileNotFoundError(f"Source path not found: {source}")
            Path(dest).parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, dest)
            row["success"] = True
            row["newPath"] = dest
        except OSError as exc:
            row["error"] = str(exc)
        results.append(row)
    ok = all(r.get("success") for r in results) if results else True
    return {
        "success": ok,
        "items": results,
        "content": f"moved {sum(1 for r in results if r.get('success'))}",
    }
