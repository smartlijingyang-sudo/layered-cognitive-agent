"""Types mirrored from @lobechat/local-file-shell/src/types.ts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal


@dataclass(slots=True)
class ReadFileResult:
    content: str
    filename: str
    file_type: str
    loc: tuple[int, int]
    char_count: int
    line_count: int
    total_char_count: int
    total_line_count: int
    created_time: datetime
    modified_time: datetime
    truncated: bool = False
    lines_truncated: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "success": not self.content.startswith("Error"),
            "content": self.content,
            "filename": self.filename,
            "fileType": self.file_type,
            "loc": list(self.loc),
            "charCount": self.char_count,
            "lineCount": self.line_count,
            "totalCharCount": self.total_char_count,
            "totalLineCount": self.total_line_count,
            "truncated": self.truncated,
            "linesTruncated": self.lines_truncated,
        }


@dataclass(slots=True)
class FileEntry:
    name: str
    path: str
    is_directory: bool
    size: int
    type: str
    created_time: datetime
    modified_time: datetime
    last_access_time: datetime

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "isDirectory": self.is_directory,
            "type": "dir" if self.is_directory else "file",
            "size": self.size,
            "fileType": self.type,
        }


@dataclass(slots=True)
class RunCommandResult:
    success: bool
    stdout: str = ""
    stderr: str = ""
    output: str = ""
    exit_code: int | None = None
    error: str = ""
    shell_id: str = ""
    duration_ms: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "output": self.output or (self.stdout + self.stderr),
            "exit_code": self.exit_code if self.exit_code is not None else 0,
            "error": self.error,
            "shell_id": self.shell_id,
            "duration_ms": self.duration_ms,
        }


SortBy = Literal["createdTime", "modifiedTime", "name", "size"]
GrepMode = Literal["content", "count", "files_with_matches"]
