"""Port of packages/local-file-shell/src/file/list.ts."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from host.local_shell.file.bind import resolve_bound
from host.local_shell.file.loaders import SYSTEM_FILES_TO_IGNORE
from host.local_shell.types import FileEntry

_SORT = {
    "name": lambda e: e.name.lower(),
    "size": lambda e: e.size,
    "modifiedTime": lambda e: e.modified_time,
    "createdTime": lambda e: e.created_time,
}


def list_local_files(payload: dict[str, Any], workspace: Path, *, mount: str) -> dict[str, Any]:
    raw = str(
        payload.get("path") or payload.get("directory_path") or payload.get("directory") or "."
    )
    dir_path = resolve_bound(raw, workspace, mount=mount, cwd=payload.get("cwd"))
    sort_by = str(payload.get("sortBy") or "modifiedTime")
    sort_order = str(payload.get("sortOrder") or "desc")
    limit = int(payload.get("limit") or 100)
    ignore_system = payload.get("ignoreSystemFiles", True)
    directory = Path(dir_path)
    if not directory.is_dir():
        return {
            "success": False,
            "error": f"not a directory: {directory.name}",
            "files": [],
            "totalCount": 0,
        }
    entries: list[FileEntry] = []
    for child in directory.iterdir():
        if ignore_system and child.name in SYSTEM_FILES_TO_IGNORE:
            continue
        try:
            stat = child.stat()
        except OSError:
            continue
        is_dir = child.is_dir()
        entries.append(
            FileEntry(
                name=child.name,
                path=str(child),
                is_directory=is_dir,
                size=stat.st_size,
                type="directory" if is_dir else child.suffix.lower().lstrip("."),
                created_time=datetime.fromtimestamp(getattr(stat, "st_ctime", stat.st_mtime)),
                modified_time=datetime.fromtimestamp(stat.st_mtime),
                last_access_time=datetime.fromtimestamp(stat.st_atime),
            )
        )
    key = _SORT.get(sort_by, _SORT["modifiedTime"])
    entries.sort(key=key, reverse=sort_order != "asc")  # type: ignore[arg-type]
    sliced = entries[: max(1, limit)]
    return {
        "success": True,
        "files": [e.as_dict() for e in sliced],
        "totalCount": len(entries),
        "content": str(len(entries)),
    }
