"""Guest scripts for search operations."""

from __future__ import annotations

import json

from lca.layer0_infra.computer.constants import (
    COMPUTER_WORKSPACE_ROOT,
    MAX_GLOB_RESULTS,
    MAX_GREP_MATCHES,
    MAX_SEARCH_RESULTS,
)
from lca.layer0_infra.computer.guest.preamble import wrap_guest_body


def build_search_files_script(
    *,
    directory: str,
    keyword: str = "",
    file_type: str = "",
    modified_after: str = "",
    modified_before: str = "",
) -> str:
    body = f"""
directory = {json.dumps(directory)}
keyword = {json.dumps(keyword)}
file_type = {json.dumps(file_type)}
modified_after = {json.dumps(modified_after)}
modified_before = {json.dumps(modified_before)}
base = _resolve(directory)
results = []
if base.is_dir():
    for root, dirs, files in _o.walk(base):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fn in files:
            if keyword and keyword.lower() not in fn.lower():
                continue
            if file_type and not fn.lower().endswith(file_type.lower().lstrip(".")):
                continue
            fp = _P(root) / fn
            try:
                st = fp.stat()
            except OSError:
                continue
            mtime = _dt.fromtimestamp(st.st_mtime).isoformat()
            if modified_after and mtime < modified_after:
                continue
            if modified_before and mtime > modified_before:
                continue
            results.append({{
                "name": fn,
                "path": str(fp),
                "isDirectory": False,
                "size": st.st_size,
            }})
            if len(results) >= {MAX_SEARCH_RESULTS}:
                break
        if len(results) >= {MAX_SEARCH_RESULTS}:
            break
result = {{"success": True, "results": results, "totalCount": len(results)}}
"""
    return wrap_guest_body(body)


def build_grep_content_script(
    *,
    pattern: str,
    directory: str,
    file_pattern: str = "",
    recursive: bool = True,
) -> str:
    body = f"""
pattern = {json.dumps(pattern)}
directory = {json.dumps(directory)}
file_pattern = {json.dumps(file_pattern)}
recursive = {json.dumps(recursive)}
base = _resolve(directory)
regex = _re.compile(pattern)
matches = []
if base.is_dir():
    iterator = base.rglob("*") if recursive else base.iterdir()
    for fp in iterator:
        if not fp.is_file():
            continue
        if file_pattern and not _fn.fnmatch(fp.name, file_pattern):
            continue
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            if regex.search(line):
                matches.append({{"path": str(fp), "line": i, "content": line[:500]}})
                if len(matches) >= {MAX_GREP_MATCHES}:
                    break
        if len(matches) >= {MAX_GREP_MATCHES}:
            break
result = {{"success": True, "matches": matches, "totalMatches": len(matches), "pattern": pattern}}
"""
    return wrap_guest_body(body)


def build_glob_files_script(*, pattern: str, directory: str = "") -> str:
    body = f"""
pattern = {json.dumps(pattern)}
directory = {json.dumps(directory or COMPUTER_WORKSPACE_ROOT)}
base = _resolve(directory)
matched = []
for fp in sorted(base.glob(pattern) if not pattern.startswith("**/") else base.glob(pattern)):
    if fp.is_file():
        matched.append({{"name": fp.name, "path": str(fp), "size": fp.stat().st_size if fp.exists() else 0}})
    if len(matched) >= {MAX_GLOB_RESULTS}:
        break
result = {{"success": True, "files": matched, "totalCount": len(matched), "pattern": pattern}}
"""
    return wrap_guest_body(body)
