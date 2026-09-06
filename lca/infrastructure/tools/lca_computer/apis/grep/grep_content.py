"""grepContent — regex search in file contents."""

from __future__ import annotations

from typing import Any


def parameters() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Regex pattern"},
            "directory": {"type": "string", "description": "Root directory"},
            "filePattern": {"type": "string", "description": "Glob filter for files"},
            "recursive": {"type": "boolean", "description": "Recurse subdirectories"},
        },
        "required": ["pattern", "directory"],
    }


DESCRIPTION = "在文件内容中进行正则搜索。参数：pattern，directory，filePattern，recursive。"
IS_IDEMPOTENT = True
