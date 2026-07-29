"""密钥脱敏与文本安全处理。

跨切面基础设施：所有可观测性输出在落盘/打印前必须经过 sanitize。
"""

from __future__ import annotations

import re
from typing import Any

_MAX_PREVIEW_LEN: int = 200
_SECRET_PATTERN: re.Pattern[str] = re.compile(
    r"(sk-|api[_-]?key[_-]?|token[_-]?)[\w-]{8,}", re.IGNORECASE
)


def sanitize(text: str) -> str:
    """过滤疑似密钥字符串。"""
    return _SECRET_PATTERN.sub("[REDACTED]", text)


def truncate(text: str, max_len: int = _MAX_PREVIEW_LEN) -> str:
    """截断过长文本。"""
    return text if len(text) <= max_len else text[:max_len] + "..."


def safe_repr(value: Any) -> Any:
    """结构化日志安全表示：原语透传，复杂对象 fallback ``repr()``。"""
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    return repr(value)
