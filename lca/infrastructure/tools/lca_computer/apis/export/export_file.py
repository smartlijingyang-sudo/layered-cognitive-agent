"""exportFile — sandbox-only: export a file for user download."""

from __future__ import annotations

from typing import Any


def parameters() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path to export"},
        },
        "required": ["path"],
    }


DESCRIPTION = "导出沙箱文件供用户下载。参数：path。"
IS_IDEMPOTENT = True
