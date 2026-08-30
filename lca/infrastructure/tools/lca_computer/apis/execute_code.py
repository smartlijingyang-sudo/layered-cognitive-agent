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
    "执行代码（支持 machine 和 sandbox 模式）。"
    "参数：description，language（python/javascript/typescript），code。"
    "在 machine 模式下通过临时文件 + 解释器执行；sandbox 模式使用原生沙箱运行时。"
)
IS_IDEMPOTENT = False
