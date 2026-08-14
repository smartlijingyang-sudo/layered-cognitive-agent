"""Port of packages/local-file-shell/src/file/edit.ts."""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

from host.local_shell.file.bind import resolve_bound


def edit_local_file(payload: dict[str, Any], workspace: Path, *, mount: str) -> dict[str, Any]:
    raw = str(payload.get("file_path") or payload.get("path") or "")
    old = str(payload.get("old_string") or payload.get("search") or "")
    new = str(payload.get("new_string") or payload.get("replace") or "")
    replace_all = bool(payload.get("replace_all") or payload.get("replaceAll"))
    file_path = resolve_bound(raw, workspace, mount=mount, cwd=payload.get("cwd"))
    try:
        content = Path(file_path).read_text(encoding="utf-8")
    except OSError as exc:
        return {"success": False, "error": str(exc), "replacements": 0}

    search, replace = old, new
    if search not in content and "\r\n" in content:
        crlf_search = search.replace("\r\n", "\n").replace("\n", "\r\n")
        if crlf_search in content:
            search = crlf_search
            replace = replace.replace("\r\n", "\n").replace("\n", "\r\n")
    if search not in content:
        return {
            "success": False,
            "error": "The specified old_string was not found in the file",
            "replacements": 0,
        }
    if replace_all:
        replacements = content.count(search)
        updated = content.replace(search, replace)
    else:
        index = content.find(search)
        updated = content[:index] + replace + content[index + len(search) :]
        replacements = 1
    Path(file_path).write_text(updated, encoding="utf-8")
    patch = "".join(
        difflib.unified_diff(
            content.splitlines(keepends=True),
            updated.splitlines(keepends=True),
            fromfile=f"a{file_path}",
            tofile=f"b{file_path}",
        )
    )
    added = sum(
        1 for line in patch.splitlines() if line.startswith("+") and not line.startswith("+++")
    )
    deleted = sum(
        1 for line in patch.splitlines() if line.startswith("-") and not line.startswith("---")
    )
    return {
        "success": True,
        "replacements": replacements,
        "diffText": f"diff --git a{file_path} b{file_path}\n{patch}",
        "linesAdded": added,
        "linesDeleted": deleted,
        "content": f"replaced {replacements} occurrence(s) in {Path(file_path).name}",
    }
