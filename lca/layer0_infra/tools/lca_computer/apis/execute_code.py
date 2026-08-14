"""executeCode — sandbox-only: execute code in the sandbox."""

from __future__ import annotations

from typing import Any


def parameters() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "description": {"type": "string", "description": "What this code does"},
            "language": {"type": "string", "enum": ["python", "javascript", "typescript"]},
            "code": {"type": "string", "description": "Code to execute"},
        },
        "required": ["description", "language", "code"],
    }


DESCRIPTION = (
    "在沙箱中执行代码。参数：description，language（python/javascript/typescript），code。"
)
IS_IDEMPOTENT = False
