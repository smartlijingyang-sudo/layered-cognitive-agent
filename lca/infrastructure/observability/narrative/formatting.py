"""运行叙事的共享格式化工具（场景卡与实时 span 行复用）。

仅承载无状态的字符串处理；不依赖任何 span 语义。
"""

from __future__ import annotations

from typing import Any


def attr_text(attrs: dict[str, Any], key: str, default: str = "") -> str:
    """统一取属性并字符串化：枚举取 ``.value``，None 回落默认值。"""
    v = attrs.get(key, default)
    if v is None:
        return default
    if hasattr(v, "value"):
        return str(v.value)
    return str(v)


def wrap_words(text: str, width: int) -> list[str]:
    """按词宽折行（先把换行压成空格）。空文本返回单空行。"""
    words = text.replace("\n", " ").split()
    if not words:
        return [""]
    rows: list[str] = []
    cur = words[0]
    for w in words[1:]:
        if len(cur) + 1 + len(w) <= width:
            cur = f"{cur} {w}"
        else:
            rows.append(cur)
            cur = w
    rows.append(cur)
    return rows
