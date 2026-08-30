"""属性策略 —— 脱敏 / 截断 / verbosity 的集中强制点。

所有 span/event 属性在写入 OTel 之前都经过本策略（facade 单点调用），
任何发射点都绕不开：脱敏不靠自觉，靠管道。
"""

from __future__ import annotations

import dataclasses
import json
import re
from enum import Enum
from typing import Any

_PREVIEW_KEYS = frozenset(
    {
        "prompt_preview",
        "response_preview",
        "subtask_preview",
        "objective_preview",
        "memory_key_preview",
        "rationale_preview",
    }
)

_SECRET_PATTERN: re.Pattern[str] = re.compile(
    r"(sk-|pk-|api[_-]?key[_-]?|token[_-]?)[\w-]{8,}", re.IGNORECASE
)
_SECRET_KEYS = frozenset({"authorization", "cookie", "set-cookie", "proxy-authorization"})

_PREVIEW_LEN_MINIMAL = 0
_PREVIEW_LEN_STANDARD = 600
_PREVIEW_LEN_VERBOSE = 100_000
"""各 verbosity 档位的预览长度上限（verbose 视为全文）。"""

_GENERIC_STR_MAX = 2_000
"""非预览类字符串属性的统一截断上限（防超大属性撑爆 trace）。"""

_CONTENT_STR_MAX = 50_000
"""journal 内容字段（``journal_kind=content``）的安全上限，不受 verbosity 档位影响。"""

_RESTRICTED_PREVIEW_MAX = 80
"""restricted/confidential 字段统一截断上限（评估文档 §49）。"""

_JOURNAL_KIND_CONTENT = "content"

_SUFFIX = "..."
_REDACTED = "[REDACTED]"


class Verbosity(str, Enum):
    """信息量档位：控制预览长度与属性丰度。"""

    MINIMAL = "minimal"
    STANDARD = "standard"
    VERBOSE = "verbose"


def sanitize(text: str) -> str:
    """过滤疑似密钥字符串。"""
    return _SECRET_PATTERN.sub(_REDACTED, text)


def truncate(text: str, max_len: int) -> str:
    """超长截断。"""
    return text if len(text) <= max_len else text[:max_len] + _SUFFIX


def redact_restricted(text: str) -> str:
    """restricted/confidential 字段的强制脱敏：截断到片段 + 标 [REDACTED]。

    写入期使用；与 verbosity 解耦，无论档位都生效（评估文档 §49、§67）。
    """
    stripped = text.replace("\r\n", "\n")
    if len(stripped) <= _RESTRICTED_PREVIEW_MAX:
        return sanitize(stripped)
    return sanitize(stripped[:_RESTRICTED_PREVIEW_MAX]) + _SUFFIX + " " + _REDACTED


def json_default(value: object) -> object:
    """``json.dumps(..., default=)``：dataclass / Enum 走结构，其余转字符串。"""
    if isinstance(value, Enum):
        return value.value
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        converted = isoformat()
        if isinstance(converted, str):
            return converted
    return str(value)


def safe_repr(value: Any) -> Any:
    """结构化安全表示：原语透传，复杂对象走 JSON 可序列化结构。"""
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    return json.loads(json.dumps(value, ensure_ascii=False, default=json_default))


def otel_safe_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
    """OTel 只接受原语；嵌套值用 stdlib ``json.dumps`` 压成字符串。"""
    out: dict[str, Any] = {}
    for key, value in attributes.items():
        if isinstance(value, (bool, int, float, str)):
            out[key] = value
        elif value is None:
            continue
        else:
            out[key] = json.dumps(value, ensure_ascii=False, default=json_default)
    return out


class AttributePolicy:
    """写入期属性策略：脱敏兜底 + verbosity 预览裁剪 + 超长截断。"""

    def __init__(self, verbosity: Verbosity = Verbosity.STANDARD, *, redact: bool = True) -> None:
        self._verbosity = verbosity
        self._redact = redact

    @property
    def verbosity(self) -> Verbosity:
        return self._verbosity

    def _preview_budget(self) -> int:
        if self._verbosity is Verbosity.MINIMAL:
            return _PREVIEW_LEN_MINIMAL
        if self._verbosity is Verbosity.VERBOSE:
            return _PREVIEW_LEN_VERBOSE
        return _PREVIEW_LEN_STANDARD

    def prepare(self, attributes: dict[str, Any]) -> dict[str, Any]:
        """批量规范化属性（脱敏/截断/类型安全）。"""
        out: dict[str, Any] = {}
        for key, value in attributes.items():
            coerced = self._prepare_value(key, value)
            if coerced is not None:
                out[key] = coerced
        return out

    def _prepare_value(self, key: str, value: Any) -> Any:
        if value is None:
            return None
        if hasattr(value, "value") and not isinstance(value, (str, int, float, bool)):
            value = value.value  # 枚举归一
        if isinstance(value, str):
            return self._prepare_str(key, value)
        if isinstance(value, (int, float, bool)):
            return value
        if isinstance(value, dict):
            return {str(k): self._prepare_value(str(k), v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._prepare_value(key, v) for v in value]
        try:
            loaded = json.loads(json.dumps(value, ensure_ascii=False, default=json_default))
        except (TypeError, ValueError):
            return self._prepare_str(key, str(value))
        if isinstance(loaded, (dict, list)):
            return self._prepare_value(key, loaded)
        if isinstance(loaded, str):
            return self._prepare_str(key, loaded)
        return loaded

    def _prepare_str(self, key: str, text: str, *, journal_kind: str | None = None) -> str | None:
        text = text.replace("\r\n", "\n")
        if self._redact and key.lower() in _SECRET_KEYS:
            return _REDACTED
        if self._redact:
            text = sanitize(text)
        if journal_kind == _JOURNAL_KIND_CONTENT:
            return truncate(text, _CONTENT_STR_MAX)
        if key in _PREVIEW_KEYS:
            budget = self._preview_budget()
            if budget <= 0:
                return None  # minimal 档不带预览
            return truncate(text, budget)
        return truncate(text, _GENERIC_STR_MAX)

    def prepare_content(self, key: str, text: str) -> tuple[str | None, bool]:
        """journal 内容字段：仅安全上限截断，不受 verbosity 影响。"""
        text = text.replace("\r\n", "\n")
        if self._redact:
            text = sanitize(text)
        truncated = len(text) > _CONTENT_STR_MAX
        return truncate(text, _CONTENT_STR_MAX), truncated
