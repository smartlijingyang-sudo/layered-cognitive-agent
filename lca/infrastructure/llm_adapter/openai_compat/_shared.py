"""OpenAI 双 Strategy 共用的响应构造与默认值。"""

from __future__ import annotations

import json
from typing import Any, NamedTuple

from lca.contracts.models.core.llm import LLMResponse, NativeToolCall, TokenUsage
from lca.infrastructure.llm_adapter.settings import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    build_generation_kwargs,
)
from lca.infrastructure.llm_adapter.tool_arguments import (
    finish_reason_value,
)

# 再导出，供策略模块与测试引用
__all__ = [
    "DEFAULT_MAX_TOKENS",
    "DEFAULT_TEMPERATURE",
    "ThinkTagStreamSplitter",
    "build_llm_response",
    "build_request_generation",
    "extract_reasoning_text",
    "pick_all_tool_calls",
    "pick_first_tool_call",
    "strip_observability_kwargs",
]

# Observability-only kwargs forwarded by TelemetryLLMAdapter — must not reach provider APIs.
_OBSERVABILITY_KWARG_KEYS = frozenset({"step", "turn"})

# Chat Completions delta 上常见的思维链字段（DeepSeek / Qwen / 兼容网关）。
_REASONING_ATTR_NAMES: tuple[str, ...] = (
    "reasoning_content",
    "reasoning",
    "reasoning_text",
    "thinking",
    "thinking_content",
)


def strip_observability_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in kwargs.items() if k not in _OBSERVABILITY_KWARG_KEYS}


def build_request_generation(
    *,
    model: str,
    has_tools: bool,
    kwargs: dict[str, Any],
) -> dict[str, Any]:
    """剥离观测 kwargs 后合并 LLMSettings 默认生成参数。"""
    cleaned = strip_observability_kwargs(kwargs)
    return build_generation_kwargs(
        model=model,
        has_tools=has_tools,
        call_kwargs=cleaned,
    )


def extract_reasoning_text(delta: Any) -> str:
    """从 Chat Completions stream delta 提取 reasoning 文本增量。

    兼容属性访问、dict、以及 SDK 的 ``model_extra`` / ``__pydantic_extra__``。
    """
    if delta is None:
        return ""
    for name in _REASONING_ATTR_NAMES:
        value = _attr_or_key(delta, name)
        if isinstance(value, str) and value:
            return value
    extra = _attr_or_key(delta, "model_extra")
    if isinstance(extra, dict):
        for name in _REASONING_ATTR_NAMES:
            value = extra.get(name)
            if isinstance(value, str) and value:
                return value
    return ""


def _attr_or_key(obj: Any, name: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(name)
    value = getattr(obj, name, None)
    if value is not None:
        return value
    # pydantic v2 extras
    extras = getattr(obj, "__pydantic_extra__", None)
    if isinstance(extras, dict):
        return extras.get(name)
    return None


_THINK_OPEN = "<think>"
_THINK_CLOSE = "</think>"


def _safe_emit_len(buf: str, tag: str) -> int:
    """buf 末尾若可能是 tag 的前缀，则暂不发出该前缀。"""
    max_hold = min(len(tag) - 1, len(buf))
    for hold in range(max_hold, 0, -1):
        if tag.startswith(buf[-hold:]):
            return len(buf) - hold
    return len(buf)


class ThinkTagStreamSplitter:
    """将 ``<think>...</think>`` 嵌入 content 的流拆成 reasoning / content 两路。

        用于 Qwen 等把思维链塞进普通 content 的模型；无标签时全部视为 content。

        边界完整性保证：
            - 成对 ``<think>...
    </think>

    ``：正常拆分
            - 孤儿 ``</think>``（无对应开标签）：**丢弃**，不泄漏到 content
            - 孤儿 ``<think>``（无闭标签）：flush 时作为 reasoning 输出
    """

    def __init__(self) -> None:
        self._buf = ""
        self._in_think = False
        self._has_opened_think = False

    def feed(self, chunk: str) -> list[tuple[str, str]]:
        """返回 ``("reasoning"|"content", text)`` 片段列表。"""
        if not chunk:
            return []
        self._buf += chunk
        out: list[tuple[str, str]] = []
        while self._buf:
            if self._in_think:
                close_at = self._buf.find(_THINK_CLOSE)
                if close_at >= 0:
                    piece = self._buf[:close_at]
                    if piece:
                        out.append(("reasoning", piece))
                    self._buf = self._buf[close_at + len(_THINK_CLOSE) :]
                    self._in_think = False
                    continue
                n = _safe_emit_len(self._buf, _THINK_CLOSE)
                if n > 0:
                    out.append(("reasoning", self._buf[:n]))
                    self._buf = self._buf[n:]
                break
            # Not in think mode — check for tags
            open_at = self._buf.find(_THINK_OPEN)
            # Also check for orphan </think> (close without open)
            close_at = self._buf.find(_THINK_CLOSE)

            # Determine which tag comes first
            first_tag_pos = -1
            first_tag_kind = ""
            if open_at >= 0 and (close_at < 0 or open_at <= close_at):
                first_tag_pos = open_at
                first_tag_kind = "open"
            elif close_at >= 0:
                first_tag_pos = close_at
                first_tag_kind = "close"

            if first_tag_kind == "open":
                # Found <think> — emit content before, enter think mode
                piece = self._buf[:first_tag_pos]
                if piece:
                    out.append(("content", piece))
                self._buf = self._buf[first_tag_pos + len(_THINK_OPEN) :]
                self._in_think = True
                self._has_opened_think = True
                continue

            if first_tag_kind == "close" and not self._has_opened_think:
                # Orphan </think> without any prior <think> — discard it entirely
                # This prevents </think> from leaking into user-visible content
                self._buf = self._buf[first_tag_pos + len(_THINK_CLOSE) :]
                continue

            if first_tag_kind == "close" and self._has_opened_think:
                # Orphan </think> after we've seen <think> before but currently not in think
                # This is a stale close tag — discard it
                self._buf = self._buf[first_tag_pos + len(_THINK_CLOSE) :]
                continue

            # No tags found — hold back potential partial tag prefix
            n = _safe_emit_len(self._buf, _THINK_OPEN)
            if n > 0:
                out.append(("content", self._buf[:n]))
                self._buf = self._buf[n:]
            break
        return out

    def flush(self) -> list[tuple[str, str]]:
        if not self._buf:
            return []
        kind = "reasoning" if self._in_think else "content"
        leftover = self._buf
        self._buf = ""
        return [(kind, leftover)]


class _RawToolCall(NamedTuple):
    name: str
    arguments_json: str
    call_id: str


def _parse_tool_arguments(arguments_json: str) -> dict[str, Any]:
    """Parse tool call arguments JSON; return empty dict on failure."""
    try:
        parsed = json.loads(arguments_json or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, ValueError):
        return {}


def build_llm_response(
    *,
    text: str,
    tool_call: _RawToolCall | None = None,
    tool_calls: list[_RawToolCall] | None = None,
    model: str,
    usage: TokenUsage | None,
    finish_reason: str | None = None,
) -> LLMResponse:
    """两 Strategy 的 complete() 尾部与 stream() 终态共用此构造函数。

    原生透传 tool_calls —— 不再编码为 JSON Decision 文本。
    支持单 tool_call（向后兼容）或 tool_calls 列表。
    """
    fr_norm = finish_reason_value(finish_reason)
    native_tool_calls: list[NativeToolCall] = []
    raw_list = tool_calls if tool_calls is not None else ([tool_call] if tool_call else [])
    for raw in raw_list:
        if raw is not None:
            native_tool_calls.append(
                NativeToolCall(
                    call_id=raw.call_id,
                    name=raw.name,
                    arguments=_parse_tool_arguments(raw.arguments_json),
                )
            )
    return LLMResponse(
        text=text,
        model=model,
        usage=usage,
        finish_reason=fr_norm,
        tool_calls=native_tool_calls,
    )


def pick_first_tool_call(
    tool_calls: dict[int, dict[str, str]],
) -> _RawToolCall | None:
    if not tool_calls:
        return None
    first = tool_calls[min(tool_calls)]
    if not first.get("name"):
        return None
    return _RawToolCall(
        name=first["name"],
        arguments_json=first.get("arguments", ""),
        call_id=first.get("id", ""),
    )


def pick_all_tool_calls(
    tool_calls: dict[int, dict[str, str]],
) -> list[_RawToolCall]:
    """Collect all accumulated streaming tool calls into a list."""
    result: list[_RawToolCall] = []
    for index in sorted(tool_calls):
        entry = tool_calls[index]
        if entry.get("name"):
            result.append(
                _RawToolCall(
                    name=entry["name"],
                    arguments_json=entry.get("arguments", ""),
                    call_id=entry.get("id", ""),
                )
            )
    return result
