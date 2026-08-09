"""OpenAI 双 Strategy 共用的响应构造与默认值。"""

from __future__ import annotations

import json
from typing import Any, NamedTuple

from lca.contracts.atoms.semantic_keys import (
    TOOL_WIRE_FINISH_REASON,
    TOOL_WIRE_INCOMPLETE,
    TOOL_WIRE_INVALID,
    TOOL_WIRE_OK,
    TOOL_WIRE_RAW_PREVIEW,
    TOOL_WIRE_REASON,
    TOOL_WIRE_STATUS,
)
from lca.contracts.models.core.llm import LLMResponse, TokenUsage
from lca.layer0_infra.llm_adapter.settings import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    build_generation_kwargs,
)
from lca.layer0_infra.llm_adapter.tool_arguments import (
    ToolArgumentsIncomplete,
    ToolArgumentsInvalid,
    ToolArgumentsOk,
    finish_reason_value,
    raw_preview,
    resolve_tool_arguments,
)

# 再导出，供策略模块与测试引用
__all__ = [
    "DEFAULT_MAX_TOKENS",
    "DEFAULT_TEMPERATURE",
    "ThinkTagStreamSplitter",
    "build_llm_response",
    "build_request_generation",
    "extract_reasoning_text",
    "pick_first_tool_call",
    "strip_observability_kwargs",
]

# Observability-only kwargs forwarded by TelemetryLLMAdapter — must not reach provider APIs.
_OBSERVABILITY_KWARG_KEYS = frozenset({"step"})

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
    """

    def __init__(self) -> None:
        self._buf = ""
        self._in_think = False

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
            open_at = self._buf.find(_THINK_OPEN)
            if open_at >= 0:
                piece = self._buf[:open_at]
                if piece:
                    out.append(("content", piece))
                self._buf = self._buf[open_at + len(_THINK_OPEN) :]
                self._in_think = True
                continue
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


_WIRE_RATIONALE_INCOMPLETE = (
    "tool_arguments_incomplete: provider truncated or JSON unclosed; "
    "do not execute; shorten args / split steps and retry"
)
_WIRE_RATIONALE_INVALID = (
    "tool_arguments_invalid: arguments JSON unusable; do not execute; fix format and retry"
)


def _encode_tool_decision(
    *,
    tool_name: str,
    rationale: str,
    outcome: ToolArgumentsOk | ToolArgumentsIncomplete | ToolArgumentsInvalid,
    finish_reason: str | None,
) -> str:
    """将 wire Outcome 编码为规范 Decision JSON（永不抛）。

    - Ok → use_tool + 真 arguments + tool_wire_status=ok
    - Incomplete/Invalid → 仍 use_tool（保留 tool_name，arguments={}），
      写入 tool_wire_* 供 Parser/Body 闸门软失败；**禁止** respond 收口。
    """
    fr = finish_reason_value(finish_reason) or finish_reason
    if isinstance(outcome, ToolArgumentsOk):
        payload: dict[str, Any] = {
            "action_type": "use_tool",
            "tool_name": tool_name,
            "arguments": outcome.arguments,
            "rationale": rationale,
            TOOL_WIRE_STATUS: TOOL_WIRE_OK,
        }
        if fr:
            payload[TOOL_WIRE_FINISH_REASON] = fr
        return json.dumps(payload, ensure_ascii=False)

    if isinstance(outcome, ToolArgumentsIncomplete):
        status = TOOL_WIRE_INCOMPLETE
        rationale_text = _WIRE_RATIONALE_INCOMPLETE
    else:
        status = TOOL_WIRE_INVALID
        rationale_text = _WIRE_RATIONALE_INVALID

    payload = {
        "action_type": "use_tool",
        "tool_name": tool_name,
        "arguments": {},
        "rationale": rationale_text if not rationale else f"{rationale_text}; {rationale}",
        TOOL_WIRE_STATUS: status,
        TOOL_WIRE_REASON: outcome.reason,
        TOOL_WIRE_RAW_PREVIEW: raw_preview(outcome.raw),
    }
    if fr:
        payload[TOOL_WIRE_FINISH_REASON] = fr
    if outcome.detail:
        payload["tool_wire_detail"] = outcome.detail
    return json.dumps(payload, ensure_ascii=False)


def build_llm_response(
    *,
    text: str,
    tool_call: _RawToolCall | None,
    model: str,
    usage: TokenUsage | None,
    finish_reason: str | None = None,
) -> LLMResponse:
    """两 Strategy 的 complete() 尾部与 stream() 终态共用此构造函数。

    tool arguments 经 :func:`resolve_tool_arguments` 三态分类后编码；
    坏 JSON / length 截断**永不** ``json.loads`` 抛穿 agent loop（ADR-0047）。
    """
    fr_norm = finish_reason_value(finish_reason)
    if tool_call is not None:
        outcome = resolve_tool_arguments(
            tool_call.arguments_json,
            finish_reason=finish_reason,
        )
        text = _encode_tool_decision(
            tool_name=tool_call.name,
            rationale=text or "",
            outcome=outcome,
            finish_reason=finish_reason,
        )
    return LLMResponse(
        text=text,
        model=model,
        usage=usage,
        finish_reason=fr_norm,
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
