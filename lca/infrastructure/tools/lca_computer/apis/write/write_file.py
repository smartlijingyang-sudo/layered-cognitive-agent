"""writeFile — write content to a file."""

from __future__ import annotations

from typing import Any


def parameters() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path to write"},
            "content": {"type": "string", "description": "File content"},
            "createDirectories": {
                "type": "boolean",
                "description": "Create parent directories",
            },
        },
        "required": ["path", "content"],
    }


DESCRIPTION = "将内容写入文件。设置 createDirectories: true 可自动创建父目录。"
IS_IDEMPOTENT = False
