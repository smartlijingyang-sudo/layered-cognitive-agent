"""Port of packages/local-file-shell/src/file/read.ts."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from host.local_shell.file.bind import resolve_bound
from host.local_shell.file.loaders import (
    SPECIAL_PARSED,
    is_readable_file_type,
    load_file,
    sniff_binary_file,
)
from host.local_shell.types import ReadFileResult

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024
MAX_OUTPUT_CHARS = 500_000
MAX_LINE_CHARS = 8_000


def _error(path: str, message: str) -> dict[str, Any]:
    name = Path(path).name
    ext = Path(path).suffix.lower().lstrip(".") or "unknown"
    result = ReadFileResult(
        content=message,
        filename=name,
        file_type=ext,
        loc=(0, 0),
        char_count=0,
        line_count=0,
        total_char_count=0,
        total_line_count=0,
        created_time=datetime.now(),
        modified_time=datetime.now(),
    )
    payload = result.as_dict()
    payload["success"] = False
    payload["error"] = message
    return payload


def read_local_file(payload: dict[str, Any], workspace: Path, *, mount: str) -> dict[str, Any]:
    raw = str(payload.get("path") or "")
    file_path = resolve_bound(raw, workspace, mount=mount, cwd=payload.get("cwd"))
    loc = payload.get("loc")
    start = payload.get("start_line")
    end = payload.get("end_line")
    if isinstance(start, int) or isinstance(end, int):
        loc = [int(start or 0), int(end or 200)]
    full = bool(payload.get("fullContent") or payload.get("full_content"))
    effective = None if full else (tuple(loc) if isinstance(loc, (list, tuple)) else (0, 200))

    path = Path(file_path)
    try:
        stats = path.stat()
    except OSError as exc:
        return _error(file_path, f"Error accessing or processing file: {exc}")
    if path.is_dir():
        return _error(file_path, "This is a directory and cannot be read as plain text.")
    if stats.st_size > MAX_FILE_SIZE_BYTES:
        return _error(
            file_path,
            f"Error: File is too large to read ({stats.st_size} bytes, limit {MAX_FILE_SIZE_BYTES}). "
            "Use grep / shell tools to inspect specific parts.",
        )
    ext = path.suffix.lower().lstrip(".")
    if ext and not is_readable_file_type(ext):
        return _error(
            file_path,
            f"Error: Unsupported binary file type: .{ext}. Use a different tool "
            "(e.g., 'runCommand' with file/hexdump/strings) to inspect binary files.",
        )
    if ext not in SPECIAL_PARSED:
        try:
            binary, reason = sniff_binary_file(file_path)
            if binary:
                return _error(
                    file_path,
                    f"Error: File appears to be binary ({reason}). Refusing to read as text.",
                )
        except OSError:
            pass

    loaded = load_file(file_path)
    if loaded.error:
        return _error(file_path, f"Error accessing or processing file: {loaded.error}")
    lines = loaded.content.split("\n")
    if effective is None:
        working, actual = lines, (0, len(lines))
    else:
        start_i, end_i = int(effective[0]), int(effective[1])
        working, actual = lines[start_i:end_i], (start_i, end_i)
    lines_truncated = 0
    capped: list[str] = []
    for line in working:
        if len(line) <= MAX_LINE_CHARS:
            capped.append(line)
            continue
        capped.append(
            f"{line[:MAX_LINE_CHARS]}… [line truncated: was {len(line)} chars, kept first {MAX_LINE_CHARS}]"
        )
        lines_truncated += 1
    content = "\n".join(capped)
    truncated = False
    if len(content) > MAX_OUTPUT_CHARS:
        original = len(content)
        content = (
            f"{content[:MAX_OUTPUT_CHARS]}\n[content truncated: response was {original} chars, "
            f"kept first {MAX_OUTPUT_CHARS}. Use a smaller line range or grep to narrow down.]"
        )
        truncated = True
    result = ReadFileResult(
        content=content,
        filename=loaded.filename,
        file_type=loaded.file_type,
        loc=(int(actual[0]), int(actual[1])),
        char_count=len(content),
        line_count=len(working),
        total_char_count=len(loaded.content),
        total_line_count=len(lines),
        created_time=loaded.created_time,
        modified_time=loaded.modified_time,
        truncated=truncated,
        lines_truncated=lines_truncated,
    )
    return result.as_dict()
