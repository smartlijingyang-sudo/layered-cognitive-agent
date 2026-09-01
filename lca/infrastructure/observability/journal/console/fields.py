"""Console projector 的纯渲染工具函数。

这些函数没有 projector 状态依赖，便于独立单元测试。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

INDENT = "    "
"""默认缩进宽度（4 空格，与既有 console 输出保持一致）。"""


def indent_block(text: str, *, prefix: str = INDENT) -> str:
    """给多行文本每行加前缀；空行不加。"""
    if not text:
        return ""
    return "\n".join(prefix + line if line else line for line in text.splitlines())


def truncate(text: str, limit: int, *, suffix: str = "...") -> str:
    """截断到 limit 字符；超出部分用 suffix 标记。"""
    if len(text) <= limit:
        return text
    return text[: max(limit - len(suffix), 0)] + suffix


def labeled(label: str, body: str, *, prefix: str = INDENT) -> str:
    """拼成 prefix + label + ': ' + body；body 多行时后续行补齐缩进。

    Example::

        >>> labeled("think", "line one\\nline two")
        '    think: line one\\n           line two'
    """
    if not body:
        return ""
    lines = body.splitlines()
    head = f"{prefix}{label}: {lines[0]}"
    if len(lines) == 1:
        return head
    continuation_indent = prefix + " " * (len(label) + 2)
    return "\n".join([head, *(continuation_indent + line for line in lines[1:] if line)])


def join_parts(parts: list[str], *, sep: str = " · ") -> str:
    """把非空 parts 用 sep 串起来；用于主行 + 可选片段的拼接。"""
    return sep.join(p for p in parts if p)


def mapping_repr(value: Any, *, limit: int = 400) -> str:
    """Mapping → repr()；非 Mapping → repr()；超长截断。

    使用 repr() 而非 json.dumps()，避免对 dataclass / set / tuple /
    非 JSON 类型的塌缩。repr() 的输出对调试更忠实。
    """
    text = repr(dict(value)) if isinstance(value, Mapping) else repr(value)
    return truncate(text, limit)


__all__ = [
    "INDENT",
    "indent_block",
    "join_parts",
    "labeled",
    "mapping_repr",
    "truncate",
]
