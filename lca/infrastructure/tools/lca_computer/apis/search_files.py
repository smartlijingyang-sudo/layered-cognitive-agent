"""searchFiles — search filenames under directory."""

from __future__ import annotations

from typing import Any


def parameters() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "directory": {"type": "string", "description": "Root directory to search"},
            "keyword": {"type": "string", "description": "Filename keyword"},
            "fileType": {"type": "string", "description": "File extension filter"},
        },
        "required": ["directory"],
    }


DESCRIPTION = "在指定目录下按文件名搜索。参数：directory，keyword，fileType。"
IS_IDEMPOTENT = True
