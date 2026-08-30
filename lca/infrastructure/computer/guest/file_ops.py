"""Static guest scripts for file operations — params arrive as JSON."""

from __future__ import annotations

from lca.infrastructure.computer.constants import READ_FILE_DEFAULT_MAX_LINES
from lca.infrastructure.computer.guest.json_script import compose_json_script
from lca.infrastructure.computer.guest.preamble import SCRIPT_PRELUDE

LIST_FILES_SCRIPT = (
    SCRIPT_PRELUDE
    + """
def main(encoded):
    args = load_args(encoded)
    directory_path = args.get("directoryPath") or ROOT
    target = resolve(directory_path)
    files = []
    if target.is_dir():
        for entry in sorted(target.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
            item = {"name": entry.name, "isDirectory": entry.is_dir(), "path": str(entry)}
            if entry.is_file():
                try:
                    item["size"] = entry.stat().st_size
                except OSError:
                    item["size"] = 0
            files.append(item)
    emit({
        "success": True,
        "files": files,
        "totalCount": len(files),
        "directoryPath": directory_path,
    })
"""
)

READ_FILE_SCRIPT = (
    SCRIPT_PRELUDE
    + """
def main(encoded):
    args = load_args(encoded)
    path = args.get("path")
    start_line = args.get("startLine")
    end_line = args.get("endLine")
    max_lines = args.get("maxLines") or 500
    target = resolve(path)
    if not target.is_file():
        emit({"success": False, "error": f"not a file: {path}", "path": path})
        return
    raw = target.read_text(encoding="utf-8", errors="replace")
    lines = raw.splitlines(keepends=True)
    total_lines = len(lines)
    s = (start_line or 1) - 1
    e = end_line if end_line is not None else min(total_lines, max_lines)
    s = max(0, min(s, total_lines))
    e = max(s, min(e, total_lines))
    chunk = "".join(lines[s:e])
    emit({
        "success": True,
        "path": path,
        "content": chunk,
        "startLine": s + 1,
        "endLine": e,
        "totalLines": total_lines,
        "charCount": len(chunk),
        "totalCharCount": len(raw),
        "filename": target.name,
        "fileType": "text",
    })
"""
)

READ_BYTES_SCRIPT = (
    SCRIPT_PRELUDE
    + """
def main(encoded):
    args = load_args(encoded)
    path = args.get("path")
    target = resolve(path)
    if not target.is_file():
        emit({"success": False, "error": f"not a file: {path}", "path": path})
        return
    raw = target.read_bytes()
    mime, _ = mimetypes.guess_type(target.name)
    emit({
        "success": True,
        "path": path,
        "filename": target.name,
        "b64": base64.b64encode(raw).decode("ascii"),
        "size": len(raw),
        "mimeType": mime or "application/octet-stream",
    })
"""
)

WRITE_FILE_SCRIPT = (
    SCRIPT_PRELUDE
    + """
def main(encoded):
    args = load_args(encoded)
    path = args.get("path")
    content = args.get("content") or ""
    create_directories = bool(args.get("createDirectories", True))
    target = resolve(path)
    if create_directories:
        target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    emit({
        "success": True,
        "path": path,
        "bytesWritten": len(content.encode("utf-8")),
    })
"""
)

EDIT_FILE_SCRIPT = (
    SCRIPT_PRELUDE
    + """
def main(encoded):
    args = load_args(encoded)
    path = args.get("path")
    search = args.get("search") or ""
    replace = args.get("replace") or ""
    replace_all = bool(args.get("all") or args.get("replaceAll") or args.get("replace_all"))
    target = resolve(path)
    if not target.is_file():
        emit({"success": False, "error": f"not a file: {path}", "path": path, "replacements": 0})
        return
    text = target.read_text(encoding="utf-8", errors="replace")
    count = text.count(search)
    if count == 0:
        emit({"success": False, "error": "search text not found", "path": path, "replacements": 0})
        return
    if replace_all:
        new_text = text.replace(search, replace)
        replacements = count
    else:
        new_text = text.replace(search, replace, 1)
        replacements = 1
    target.write_text(new_text, encoding="utf-8")
    emit({
        "success": True,
        "path": path,
        "replacements": replacements,
        "linesAdded": max(0, new_text.count("\\n") - text.count("\\n")),
        "linesDeleted": max(0, text.count("\\n") - new_text.count("\\n")),
    })
"""
)

MOVE_FILES_SCRIPT = (
    SCRIPT_PRELUDE
    + """
def main(encoded):
    args = load_args(encoded)
    operations = args.get("operations") or []
    results = []
    for op in operations:
        src = resolve(op.get("source", ""))
        dst = resolve(op.get("destination", ""))
        entry = {"source": op.get("source", ""), "destination": op.get("destination", ""), "success": False}
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            entry["success"] = True
        except Exception as exc:
            entry["error"] = str(exc)
        results.append(entry)
    success_count = sum(1 for r in results if r.get("success"))
    emit({
        "success": success_count == len(results) and len(results) > 0,
        "results": results,
        "successCount": success_count,
        "totalCount": len(results),
    })
"""
)


def build_list_files_script(*, directory_path: str) -> str:
    return compose_json_script(LIST_FILES_SCRIPT, {"directoryPath": directory_path})


def build_read_file_script(
    *,
    path: str,
    start_line: int | None = None,
    end_line: int | None = None,
) -> str:
    return compose_json_script(
        READ_FILE_SCRIPT,
        {
            "path": path,
            "startLine": start_line,
            "endLine": end_line,
            "maxLines": READ_FILE_DEFAULT_MAX_LINES,
        },
    )


def build_read_bytes_script(*, path: str) -> str:
    return compose_json_script(READ_BYTES_SCRIPT, {"path": path})


def build_write_file_script(
    *,
    path: str,
    content: str,
    create_directories: bool = True,
) -> str:
    return compose_json_script(
        WRITE_FILE_SCRIPT,
        {
            "path": path,
            "content": content,
            "createDirectories": create_directories,
        },
    )


def build_edit_file_script(
    *,
    path: str,
    search: str,
    replace: str,
    replace_all: bool = False,
) -> str:
    return compose_json_script(
        EDIT_FILE_SCRIPT,
        {
            "path": path,
            "search": search,
            "replace": replace,
            "all": replace_all,
        },
    )


def build_move_files_script(*, operations: list[dict[str, str]]) -> str:
    return compose_json_script(MOVE_FILES_SCRIPT, {"operations": operations})
