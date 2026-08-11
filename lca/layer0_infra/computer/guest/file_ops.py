"""Guest scripts for file operations."""

from __future__ import annotations

import json

from lca.layer0_infra.computer.constants import READ_FILE_DEFAULT_MAX_LINES
from lca.layer0_infra.computer.guest.preamble import wrap_guest_body


def build_list_files_script(*, directory_path: str) -> str:
    body = f"""
directory_path = {json.dumps(directory_path)}
target = _resolve(directory_path)
files = []
if target.is_dir():
    for entry in sorted(target.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
        item = {{"name": entry.name, "isDirectory": entry.is_dir(), "path": str(entry)}}
        if entry.is_file():
            try:
                item["size"] = entry.stat().st_size
            except OSError:
                item["size"] = 0
        files.append(item)
result = {{"success": True, "files": files, "totalCount": len(files), "directoryPath": directory_path}}
"""
    return wrap_guest_body(body)


def build_read_file_script(
    *,
    path: str,
    start_line: int | None = None,
    end_line: int | None = None,
) -> str:
    body = f"""
path = {json.dumps(path)}
start_line = {json.dumps(start_line)}
end_line = {json.dumps(end_line)}
target = _resolve(path)
if not target.is_file():
    result = {{"success": False, "error": f"not a file: {{path}}", "path": path}}
else:
    raw = target.read_text(encoding="utf-8", errors="replace")
    lines = raw.splitlines(keepends=True)
    total_lines = len(lines)
    s = (start_line or 1) - 1
    e = end_line if end_line is not None else min(total_lines, {READ_FILE_DEFAULT_MAX_LINES})
    s = max(0, min(s, total_lines))
    e = max(s, min(e, total_lines))
    chunk = "".join(lines[s:e])
    result = {{
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
    }}
"""
    return wrap_guest_body(body)


def build_write_file_script(
    *,
    path: str,
    content: str,
    create_directories: bool = True,
) -> str:
    body = f"""
path = {json.dumps(path)}
content = {json.dumps(content)}
create_directories = {json.dumps(create_directories)}
target = _resolve(path)
if create_directories:
    target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(content, encoding="utf-8")
result = {{
    "success": True,
    "path": path,
    "bytesWritten": len(content.encode("utf-8")),
}}
"""
    return wrap_guest_body(body)


def build_edit_file_script(
    *,
    path: str,
    search: str,
    replace: str,
    replace_all: bool = False,
) -> str:
    body = f"""
path = {json.dumps(path)}
search = {json.dumps(search)}
replace = {json.dumps(replace)}
replace_all = {json.dumps(replace_all)}
target = _resolve(path)
if not target.is_file():
    result = {{"success": False, "error": f"not a file: {{path}}", "path": path, "replacements": 0}}
else:
    text = target.read_text(encoding="utf-8", errors="replace")
    count = text.count(search)
    if count == 0:
        result = {{"success": False, "error": "search text not found", "path": path, "replacements": 0}}
    else:
        if replace_all:
            new_text = text.replace(search, replace)
            replacements = count
        else:
            new_text = text.replace(search, replace, 1)
            replacements = 1
        target.write_text(new_text, encoding="utf-8")
        result = {{
            "success": True,
            "path": path,
            "replacements": replacements,
            "linesAdded": max(0, new_text.count("\\n") - text.count("\\n")),
            "linesDeleted": max(0, text.count("\\n") - new_text.count("\\n")),
        }}
"""
    return wrap_guest_body(body)


def build_move_files_script(*, operations: list[dict[str, str]]) -> str:
    ops_literal = json.dumps(operations, ensure_ascii=False)
    body = f"""
operations = {ops_literal}
results = []
for op in operations:
    src = _resolve(op.get("source", ""))
    dst = _resolve(op.get("destination", ""))
    entry = {{"source": op.get("source", ""), "destination": op.get("destination", ""), "success": False}}
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        _sh.move(str(src), str(dst))
        entry["success"] = True
    except Exception as exc:
        entry["error"] = str(exc)
    results.append(entry)
success_count = sum(1 for r in results if r.get("success"))
result = {{
    "success": success_count == len(results) and len(results) > 0,
    "results": results,
    "successCount": success_count,
    "totalCount": len(results),
}}
"""
    return wrap_guest_body(body)
