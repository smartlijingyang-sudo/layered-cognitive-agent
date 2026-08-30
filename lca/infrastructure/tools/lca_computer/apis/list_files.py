"""listFiles — list files and directories."""

from __future__ import annotations

from typing import Any


def parameters() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "directoryPath": {"type": "string", "description": "The directory path to list"},
        },
        "required": ["directoryPath"],
    }


DESCRIPTION = "列出指定目录下的文件和子目录。在假设文件路径之前先使用此工具确认目录结构。"
IS_IDEMPOTENT = True
