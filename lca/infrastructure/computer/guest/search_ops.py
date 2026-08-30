"""Static guest scripts for search operations — params arrive as JSON."""

from __future__ import annotations

from lca.infrastructure.computer.constants import (
    MAX_GLOB_RESULTS,
    MAX_GREP_MATCHES,
    MAX_SEARCH_RESULTS,
)
from lca.infrastructure.computer.guest.json_script import compose_json_script
from lca.infrastructure.computer.guest.preamble import SCRIPT_PRELUDE
from lca.infrastructure.sandbox.paths import ONLYBOXES

SEARCH_FILES_SCRIPT = (
    SCRIPT_PRELUDE
    + """
def main(encoded):
    args = load_args(encoded)
    directory = args.get("directory") or ROOT
    keyword = args.get("keyword") or ""
    file_type = args.get("fileType") or ""
    modified_after = args.get("modifiedAfter") or ""
    modified_before = args.get("modifiedBefore") or ""
    limit = args.get("limit") or 200
    base = resolve(directory)
    results = []
    if base.is_dir():
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for fn in files:
                if keyword and keyword.lower() not in fn.lower():
                    continue
                if file_type and not fn.lower().endswith(file_type.lower().lstrip(".")):
                    continue
                fp = Path(root) / fn
                try:
                    st = fp.stat()
                except OSError:
                    continue
                mtime = datetime.fromtimestamp(st.st_mtime).isoformat()
                if modified_after and mtime < modified_after:
                    continue
                if modified_before and mtime > modified_before:
                    continue
                results.append({
                    "name": fn,
                    "path": str(fp),
                    "isDirectory": False,
                    "size": st.st_size,
                })
                if len(results) >= limit:
                    break
            if len(results) >= limit:
                break
    emit({"success": True, "results": results, "totalCount": len(results)})
"""
)

GREP_CONTENT_SCRIPT = (
    SCRIPT_PRELUDE
    + """
def main(encoded):
    args = load_args(encoded)
    pattern = args.get("pattern") or ""
    directory = args.get("directory") or ROOT
    file_pattern = args.get("filePattern") or ""
    recursive = args.get("recursive", True)
    limit = args.get("limit") or 200
    base = resolve(directory)
    regex = re.compile(pattern)
    matches = []
    if base.is_dir():
        iterator = base.rglob("*") if recursive else base.iterdir()
        for fp in iterator:
            if not fp.is_file():
                continue
            if file_pattern and not fnmatch.fnmatch(fp.name, file_pattern):
                continue
            try:
                text = fp.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for i, line in enumerate(text.splitlines(), start=1):
                if regex.search(line):
                    matches.append({"path": str(fp), "line": i, "content": line[:500]})
                    if len(matches) >= limit:
                        break
            if len(matches) >= limit:
                break
    emit({
        "success": True,
        "matches": matches,
        "totalMatches": len(matches),
        "pattern": pattern,
    })
"""
)

GLOB_FILES_SCRIPT = (
    SCRIPT_PRELUDE
    + """
def main(encoded):
    args = load_args(encoded)
    pattern = args.get("pattern") or "*"
    directory = args.get("directory") or ROOT
    limit = args.get("limit") or 1000
    base = resolve(directory)
    matched = []
    for fp in sorted(base.glob(pattern)):
        if fp.is_file():
            matched.append({
                "name": fp.name,
                "path": str(fp),
                "size": fp.stat().st_size if fp.exists() else 0,
            })
        if len(matched) >= limit:
            break
    emit({
        "success": True,
        "files": matched,
        "totalCount": len(matched),
        "pattern": pattern,
    })
"""
)


def build_search_files_script(
    *,
    directory: str,
    keyword: str = "",
    file_type: str = "",
    modified_after: str = "",
    modified_before: str = "",
) -> str:
    return compose_json_script(
        SEARCH_FILES_SCRIPT,
        {
            "directory": directory,
            "keyword": keyword,
            "fileType": file_type,
            "modifiedAfter": modified_after,
            "modifiedBefore": modified_before,
            "limit": MAX_SEARCH_RESULTS,
        },
    )


def build_grep_content_script(
    *,
    pattern: str,
    directory: str,
    file_pattern: str = "",
    recursive: bool = True,
) -> str:
    return compose_json_script(
        GREP_CONTENT_SCRIPT,
        {
            "pattern": pattern,
            "directory": directory,
            "filePattern": file_pattern,
            "recursive": recursive,
            "limit": MAX_GREP_MATCHES,
        },
    )


def build_glob_files_script(*, pattern: str, directory: str = "") -> str:
    return compose_json_script(
        GLOB_FILES_SCRIPT,
        {
            "pattern": pattern,
            "directory": directory or ONLYBOXES.root,
            "limit": MAX_GLOB_RESULTS,
        },
    )
