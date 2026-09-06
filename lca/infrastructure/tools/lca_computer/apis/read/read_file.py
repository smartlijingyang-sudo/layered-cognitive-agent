"""readFile — read file content."""

from __future__ import annotations

from typing import Any


def parameters() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path to read"},
            "startLine": {"type": "number", "description": "Start line (1-based)"},
            "endLine": {"type": "number", "description": "End line (1-based)"},
        },
        "required": ["path"],
    }


DESCRIPTION = "读取文件内容。参数：path，可选 startLine/endLine（从 1 开始的行号）。"
IS_IDEMPOTENT = True
