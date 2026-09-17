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
    "在沙箱执行代码。每次调用是新的解释器（上一轮变量不在内存里）；工作区文件会保留。"
    "产出写到 outputs/ 后自动收集。画图中文已预配置，不要改 font.sans-serif，不要 fc-list。"
    "PDF 用 reportlab 的 STSong-Light。参数：description，language（python/javascript/typescript），code。"
)
IS_IDEMPOTENT = False
