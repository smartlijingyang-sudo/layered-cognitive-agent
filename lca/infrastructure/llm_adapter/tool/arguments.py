"""工具调用 arguments wire 防腐 —— 纯函数、三态 Outcome（ADR-0047）。

LLM function-call 的 ``arguments`` 是不可信外部字符串：可能被
``max_tokens`` 截断（Unterminated string），也可能结构非法。

本模块**只做解析与分类**，不执行工具、不改写为 respond、不静默「修完就跑」。

Outcome::

    Ok(arguments)           — 完整可执行
    Incomplete(raw, reason) — 截断 / finish_reason=length
    Invalid(raw, error)     — 结构不可用且无法判定为截断

调用方（``build_llm_response``）将 Outcome 编码为规范 Decision 载荷；
Body 闸门拒绝 incomplete/invalid，回灌 ``Observation(success=False)``。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from lca.contracts.atoms.enums.enums import FinishReason

# 诊断预览上限，防止超大 raw 污染 journal / Decision.extra
_RAW_PREVIEW_MAX = 2000

# Keys whose values are opaque text bodies. Truncated JSON still carries
# these as unclosed strings; recovering them is how coding agents land a
# Write/Bash/execute call instead of executing ``{}``.
_PARTIAL_STRING_KEYS = (
    "path",
    "name",
    "content",
    "code",
    "command",
    "description",
    "language",
    "skill_id",
    "query",
)

ToolWireReason = Literal[
    "finish_reason_length",
    "unterminated_or_truncated_json",
    "invalid_json",
    "empty_arguments",
]


@dataclass(frozen=True, slots=True)
class ToolArgumentsOk:
    """完整解析的 tool arguments。"""

    arguments: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ToolArgumentsIncomplete:
    """参数不完整：禁止执行工具，应回灌失败观测。"""

    raw: str
    reason: ToolWireReason
    detail: str = ""


@dataclass(frozen=True, slots=True)
class ToolArgumentsInvalid:
    """参数非法且非明确截断：禁止执行，应回灌失败观测。"""

    raw: str
    reason: ToolWireReason
    detail: str = ""


ToolArgumentsOutcome = ToolArgumentsOk | ToolArgumentsIncomplete | ToolArgumentsInvalid

# finish_reason / status / incomplete_details.reason → FinishReason
_FINISH_REASON_ALIASES: dict[str, FinishReason] = {
    "stop": FinishReason.STOP,
    "end_turn": FinishReason.STOP,
    "completed": FinishReason.STOP,
    "length": FinishReason.LENGTH,
    "max_tokens": FinishReason.LENGTH,
    "max_output_tokens": FinishReason.LENGTH,
    "incomplete": FinishReason.LENGTH,
    "tool_calls": FinishReason.TOOL_CALLS,
    "tool_use": FinishReason.TOOL_CALLS,
    "function_call": FinishReason.TOOL_CALLS,
    "content_filter": FinishReason.CONTENT_FILTER,
    "content_filtered": FinishReason.CONTENT_FILTER,
    "error": FinishReason.ERROR,
    "failed": FinishReason.ERROR,
}


def normalize_finish_reason(raw: str | None) -> FinishReason:
    """将各 provider 的 finish/stop/status 字符串归一为 :class:`FinishReason`。"""
    if raw is None:
        return FinishReason.UNKNOWN
    key = str(raw).strip().lower()
    if not key:
        return FinishReason.UNKNOWN
    return _FINISH_REASON_ALIASES.get(key, FinishReason.UNKNOWN)


def raw_preview(raw: str, *, max_len: int = _RAW_PREVIEW_MAX) -> str:
    if len(raw) <= max_len:
        return raw
    return raw[:max_len]


def extract_partial_json_string(raw: str, key: str) -> str | None:
    """Return the decoded JSON string value for ``key``, even if unclosed."""
    marker = f'"{key}"'
    idx = raw.find(marker)
    if idx < 0:
        return None
    colon = raw.find(":", idx + len(marker))
    if colon < 0:
        return None
    rest = raw[colon + 1 :].lstrip()
    if not rest.startswith('"'):
        return None
    return _decode_json_string_prefix(rest, 1)


def recover_partial_tool_arguments(raw: str) -> dict[str, Any]:
    """Recover ``path`` / ``content`` / ``code`` from truncated tool JSON.

    Strict ``json.loads`` fails on an unterminated string. Coding-agent
    Write/execute paths still need the destination and the body so the
    sandbox can land the file (it already chunks large writes). Empty
    recovery stays empty.
    """
    stripped = (raw or "").strip()
    if not stripped:
        return {}
    try:
        parsed: Any = json.loads(stripped)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict):
        return dict(parsed)
    if parsed is not None:
        return {"_value": parsed}
    out: dict[str, Any] = {}
    for key in _PARTIAL_STRING_KEYS:
        value = extract_partial_json_string(raw, key)
        if value is not None:
            out[key] = value
    return out


def _usable_recovered_arguments(arguments: dict[str, Any]) -> bool:
    return any(
        isinstance(arguments.get(key), str) and str(arguments[key]).strip()
        for key in _PARTIAL_STRING_KEYS
    )


def _decode_json_string_prefix(source: str, start: int) -> str:
    parts: list[str] = []
    escaped = False
    for ch in source[start:]:
        if escaped:
            if ch == "n":
                parts.append("\n")
            elif ch == "t":
                parts.append("\t")
            elif ch == "r":
                parts.append("\r")
            else:
                parts.append(ch)
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == '"':
            break
        parts.append(ch)
    return "".join(parts)


def resolve_tool_arguments(
    arguments_json: str | None,
    *,
    finish_reason: str | None = None,
) -> ToolArgumentsOutcome:
    """解析 tool arguments 并分类。

    规则（按优先级）::

        1. 空 arguments + tool_calls 结束 → Incomplete(empty_arguments)
        2. 空 arguments（其它结束原因）   → Ok({})
        3. json.loads 成功且 dict         → Ok（含 finish_reason=length）
        4. json.loads 成功非 dict         → Ok({"_value": ...})
        5. JSONDecodeError 且能抽出 path/content/code 等 → Ok(recovered)
        6. 其余 JSONDecodeError / length 且无法抽出     → Incomplete
    """
    fr = normalize_finish_reason(finish_reason)
    raw = arguments_json if arguments_json is not None else ""

    if not str(raw).strip():
        if fr is FinishReason.TOOL_CALLS or fr is FinishReason.LENGTH:
            return ToolArgumentsIncomplete(
                raw=raw,
                reason="empty_arguments"
                if fr is FinishReason.TOOL_CALLS
                else "finish_reason_length",
                detail="provider ended a tool call with empty arguments JSON",
            )
        return ToolArgumentsOk(arguments={})

    try:
        parsed: Any = json.loads(raw)
    except json.JSONDecodeError:
        parsed = None
    else:
        if isinstance(parsed, dict):
            return ToolArgumentsOk(arguments=dict(parsed))
        return ToolArgumentsOk(arguments={"_value": parsed})

    # Strict parse failed: ``raw`` is a truncated stream. Recovery is keyed on
    # opaque text bodies because those are the arguments a coding agent cannot
    # afford to lose; a payload that parses never reaches this branch, so its
    # key names are not gated by ``_PARTIAL_STRING_KEYS``.
    recovered = recover_partial_tool_arguments(raw)
    if _usable_recovered_arguments(recovered):
        return ToolArgumentsOk(arguments=recovered)

    if fr is FinishReason.LENGTH:
        return ToolArgumentsIncomplete(
            raw=raw,
            reason="finish_reason_length",
            detail="provider finish_reason=length and no recoverable tool fields",
        )
    return ToolArgumentsIncomplete(
        raw=raw,
        reason="unterminated_or_truncated_json",
        detail="arguments JSON is not an object and no path/content/code fields recovered",
    )


def finish_reason_value(raw: str | None) -> str | None:
    """供 ``LLMResponse.finish_reason`` 写入的规范字符串；未知且空输入时 None。"""
    if raw is None or not str(raw).strip():
        return None
    return normalize_finish_reason(raw).value
