"""Convert internal run failures into stable user-facing error messages."""

from __future__ import annotations

import re

_SANITIZE_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"DataInspectionFailed|content.?filter|inappropriate.?content|content.?safety",
            re.IGNORECASE,
        ),
        "模型输出触发了内容安全策略，请调整输入后重试",
    ),
    (
        re.compile(r"<\d{3}>|APIError|APIConnectionError|APITimeoutError|InternalError"),
        "模型服务暂时不可用，请稍后重试",
    ),
    (
        re.compile(r"timeout|connection|network", re.IGNORECASE),
        "网络连接异常，请检查网络后重试",
    ),
)

_INTERNAL_EXCEPTION_PREFIX = re.compile(r"^_*[A-Z][A-Za-z0-9._]*Error:\s*")


def sanitize_error(error: str) -> str:
    """Map known provider failures to safe, actionable messages."""

    if not error:
        return error
    for pattern, replacement in _SANITIZE_RULES:
        if pattern.search(error):
            return replacement
    return error


def format_user_error(error: str, *, run_id: str, trace_id: str) -> str:
    """Attach user-safe failure text to the trace context needed for support."""

    user_facing = _strip_internal_exception_prefix(sanitize_error(error))
    return f"{user_facing}\nrun: {run_id} | trace: {trace_id}"


def _strip_internal_exception_prefix(error: str) -> str:
    """Remove one leading Python exception type from an error message."""

    return _INTERNAL_EXCEPTION_PREFIX.sub("", error or "", count=1)


__all__ = ["format_user_error", "sanitize_error"]
