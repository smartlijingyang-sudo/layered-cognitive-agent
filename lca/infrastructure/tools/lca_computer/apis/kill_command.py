"""killCommand — kill a background command."""

from __future__ import annotations

from typing import Any


def parameters() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "commandId": {"type": "string", "description": "Background command ID"},
        },
        "required": ["commandId"],
    }


DESCRIPTION = "终止一个后台命令。参数：commandId。"
IS_IDEMPOTENT = False
