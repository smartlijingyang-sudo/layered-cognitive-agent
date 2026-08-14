"""Port of packages/local-file-shell/src/file/rename.ts."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from host.local_shell.file.bind import resolve_bound

_BAD_NAME = re.compile(r'["*/:<>?\\|]')


def rename_local_file(payload: dict[str, Any], workspace: Path, *, mount: str) -> dict[str, Any]:
    raw = str(payload.get("path") or "")
    new_name = str(payload.get("newName") or payload.get("new_name") or "")
    if not raw or not new_name:
        return {"success": False, "error": "Both path and newName are required.", "newPath": ""}
    if "/" in new_name or "\\" in new_name or new_name in {".", ".."} or _BAD_NAME.search(new_name):
        return {
            "success": False,
            "error": "Invalid new name. It cannot contain path separators or reserved characters.",
            "newPath": "",
        }
    current = resolve_bound(raw, workspace, mount=mount)
    dest = str(Path(current).with_name(new_name))
    if os.path.normpath(current) == os.path.normpath(dest):
        return {"success": True, "newPath": dest}
    try:
        os.rename(current, dest)
        return {"success": True, "newPath": dest, "content": dest}
    except OSError as exc:
        return {"success": False, "error": str(exc), "newPath": ""}
