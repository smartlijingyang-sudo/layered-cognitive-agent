"""moveFiles — move or rename files."""

from __future__ import annotations

from typing import Any


def parameters() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "operations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "source": {"type": "string"},
                        "destination": {"type": "string"},
                    },
                    "required": ["source", "destination"],
                },
            },
        },
        "required": ["operations"],
    }


DESCRIPTION = "移动或重命名文件。参数：operations[{source, destination}]。"
IS_IDEMPOTENT = False
