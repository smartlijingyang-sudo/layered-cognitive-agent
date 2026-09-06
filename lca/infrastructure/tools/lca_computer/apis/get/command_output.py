"""getCommandOutput — poll output from a background runCommand."""

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


DESCRIPTION = "轮询后台命令的输出。参数：commandId。"
IS_IDEMPOTENT = True
