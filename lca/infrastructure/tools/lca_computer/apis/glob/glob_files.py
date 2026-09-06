"""globFiles — glob match files."""

from __future__ import annotations

from typing import Any


def parameters() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Glob pattern"},
            "directory": {"type": "string", "description": "Root directory"},
        },
        "required": ["pattern"],
    }


DESCRIPTION = "按 glob 模式匹配文件。参数：pattern，directory。"
IS_IDEMPOTENT = True
