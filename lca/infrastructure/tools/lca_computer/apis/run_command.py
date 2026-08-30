"""runCommand — execute a shell command with timeout control."""

from __future__ import annotations

from typing import Any


def parameters() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "description": {"type": "string", "description": "What this command does"},
            "command": {"type": "string", "description": "Shell command to execute"},
            "background": {"type": "boolean", "description": "Run in background"},
            "timeout": {"type": "number", "description": "Timeout (seconds)"},
        },
        "required": ["description", "command"],
    }


DESCRIPTION = (
    "执行 shell 命令，支持超时控制。"
    "支持后台执行（background: true → 返回 commandId）。"
    "参数：description，command，background，timeout。"
)
IS_IDEMPOTENT = False
