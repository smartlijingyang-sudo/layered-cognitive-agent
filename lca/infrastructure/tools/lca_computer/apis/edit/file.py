"""editFile — exact string replacement in a file."""

from __future__ import annotations

from typing import Any


def parameters() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path to edit"},
            "search": {"type": "string", "description": "Text to search for"},
            "replace": {"type": "string", "description": "Replacement text"},
            "all": {"type": "boolean", "description": "Replace all occurrences"},
        },
        "required": ["path", "search", "replace"],
    }


DESCRIPTION = "在文件中进行精确的字符串替换。使用前必须先读取文件内容。"
IS_IDEMPOTENT = False
