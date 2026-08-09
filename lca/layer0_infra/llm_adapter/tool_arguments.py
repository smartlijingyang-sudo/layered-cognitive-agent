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

from lca.contracts.atoms.enums import FinishReason

# 诊断预览上限，防止超大 raw 污染 journal / Decision.extra
_RAW_PREVIEW_MAX = 2000

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


def resolve_tool_arguments(
    arguments_json: str | None,
    *,
    finish_reason: str | None = None,
) -> ToolArgumentsOutcome:
    """解析 tool arguments 并分类。

    规则（按优先级）::

        1. finish_reason ≡ LENGTH  → Incomplete（即使 JSON 碰巧可 parse）
        2. 空 arguments            → Ok({})
        3. json.loads 成功且 dict  → Ok
        4. json.loads 成功非 dict  → Ok({"_value": ...})  # 极少数 provider 形态
        5. JSONDecodeError         → Incomplete（截断信号）或 Invalid
    """
    fr = normalize_finish_reason(finish_reason)
    raw = arguments_json if arguments_json is not None else ""

    if fr is FinishReason.LENGTH:
        return ToolArgumentsIncomplete(
            raw=raw,
            reason="finish_reason_length",
            detail="provider finish_reason=length; tool arguments treated as incomplete",
        )

    if not str(raw).strip():
        return ToolArgumentsOk(arguments={})

    try:
        parsed: Any = json.loads(raw)
    except json.JSONDecodeError as exc:
        # Unterminated string / Extra data 等均视为不完整 wire，禁止执行
        return ToolArgumentsIncomplete(
            raw=raw,
            reason="unterminated_or_truncated_json",
            detail=f"{exc.msg} (pos {exc.pos})",
        )

    if isinstance(parsed, dict):
        return ToolArgumentsOk(arguments=dict(parsed))
    return ToolArgumentsOk(arguments={"_value": parsed})


def finish_reason_value(raw: str | None) -> str | None:
    """供 ``LLMResponse.finish_reason`` 写入的规范字符串；未知且空输入时 None。"""
    if raw is None or not str(raw).strip():
        return None
    return normalize_finish_reason(raw).value
