"""Error sanitization layer — 内部错误脱敏。

将 LLM API、内部服务的原始错误消息转换为用户友好的提示。

设计原则：
  1. Chain of Responsibility — 多个 Sanitizer 按序尝试
  2. 开闭原则 — 新增错误类型只需添加 Sanitizer，不改现有代码
  3. 默认 fallback — 无匹配时返回原始错误（不丢失信息）
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SanitizeResult:
    """脱敏结果。"""

    matched: bool
    message: str = ""


class ErrorSanitizer(Protocol):
    """错误脱敏器接口。"""

    def sanitize(self, error: str) -> SanitizeResult:
        """尝试脱敏。matched=True 表示命中，message 为脱敏后的消息。"""
        ...


@dataclass(frozen=True)
class RegexSanitizer:
    """基于正则匹配的脱敏器。"""

    pattern: str
    replacement: str
    flags: int = re.IGNORECASE

    def sanitize(self, error: str) -> SanitizeResult:
        if re.search(self.pattern, error, self.flags):
            return SanitizeResult(matched=True, message=self.replacement)
        return SanitizeResult(matched=False)


@dataclass(frozen=True)
class PassthroughSanitizer:
    """默认 fallback — 原样返回。"""

    def sanitize(self, error: str) -> SanitizeResult:
        return SanitizeResult(matched=True, message=error)


class SanitizerChain:
    """脱敏器链 — Chain of Responsibility。"""

    def __init__(self, sanitizers: list[ErrorSanitizer]) -> None:
        self._sanitizers = sanitizers

    def sanitize(self, error: str) -> str:
        """按序尝试脱敏，首个命中即返回。"""
        if not error:
            return error
        for sanitizer in self._sanitizers:
            result = sanitizer.sanitize(error)
            if result.matched:
                return result.message
        return error  # 无 sanitizer 命中时原样返回


# ── 默认脱敏器链 ──────────────────────────────────────────────────

_DEFAULT_CHAIN = SanitizerChain(
    [
        # 内容审查类错误
        RegexSanitizer(
            pattern=r"DataInspectionFailed|content.?filter|inappropriate.?content|content.?safety",
            replacement="模型输出触发了内容安全策略，请调整输入后重试",
        ),
        # LLM API 通用错误
        RegexSanitizer(
            pattern=r"<\d{3}>|APIError|APIConnectionError|APITimeoutError|InternalError",
            replacement="模型服务暂时不可用，请稍后重试",
        ),
        # 网络/超时类
        RegexSanitizer(
            pattern=r"timeout|connection|network",
            replacement="网络连接异常，请检查网络后重试",
        ),
        # 默认 fallback
        PassthroughSanitizer(),
    ]
)


def sanitize_error(error: str) -> str:
    """脱敏错误消息，供 projection 层调用。"""
    return _DEFAULT_CHAIN.sanitize(error)
