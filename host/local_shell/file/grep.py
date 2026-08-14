"""Port of packages/local-file-shell/src/file/grep.ts (rg + python fallback)."""

from __future__ import annotations

import contextlib
import fnmatch
import shutil
import subprocess
from pathlib import Path
from typing import Any

from host.local_shell.file.bind import resolve_bound
from host.local_shell.file.has_hidden import has_hidden_segment


def grep_content(payload: dict[str, Any], workspace: Path, *, mount: str) -> dict[str, Any]:
    pattern = str(payload.get("pattern") or "")
    scope = (
        payload.get("scope")
        or payload.get("path")
        or payload.get("directory")
        or payload.get("cwd")
        or "."
    )
    file_pattern = str(
        payload.get("glob") or payload.get("filePattern") or payload.get("file_pattern") or ""
    )
    output_mode = str(payload.get("output_mode") or "files_with_matches")
    directory = Path(resolve_bound(str(scope), workspace, mount=mount))
    wants_hidden = has_hidden_segment(file_pattern)
    hint = (
        "Auto-enabled hidden-file matching because filePattern contains a dot-prefixed segment."
        if wants_hidden
        else None
    )
    rg = shutil.which("rg")
    if rg:
        args = [rg, "--color=never", "--no-heading", "--with-filename", "--max-columns", "500"]
        if wants_hidden:
            args.extend(["--hidden", "--glob", "!**/.git/**"])
        if output_mode == "files_with_matches":
            args.append("--files-with-matches")
        elif output_mode == "count":
            args.append("--count")
        else:
            args.extend(["--line-number", "--column"])
        if file_pattern:
            args.extend(["--glob", file_pattern])
        args.extend([pattern, "."])
        proc = subprocess.run(args, cwd=directory, capture_output=True, text=True, check=False)  # noqa: S603
        if proc.returncode not in {0, 1}:
            return {
                "success": False,
                "engine": "rg",
                "matches": [],
                "total_matches": 0,
                "hint": hint,
            }
        matches = [line for line in proc.stdout.splitlines() if line]
        total = len(matches)
        if output_mode == "count":
            total = 0
            for line in matches:
                with contextlib.suppress(ValueError):
                    total += int(line.rsplit(":", 1)[-1])
        return {
            "success": True,
            "engine": "rg",
            "matches": matches,
            "total_matches": total,
            "content": str(total),
            "hint": hint,
        }
    matches: list[str] = []
    glob = file_pattern or "*"
    for path in directory.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        if not fnmatch.fnmatch(path.name, glob):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if output_mode == "files_with_matches":
            if pattern in text:
                matches.append(str(path))
        else:
            for idx, line in enumerate(text.splitlines(), start=1):
                if pattern in line:
                    matches.append(f"{path}:{idx}:{line}")
        if len(matches) >= 200:
            break
    return {
        "success": True,
        "engine": "python",
        "matches": matches,
        "total_matches": len(matches),
        "content": str(len(matches)),
        "hint": hint,
    }
