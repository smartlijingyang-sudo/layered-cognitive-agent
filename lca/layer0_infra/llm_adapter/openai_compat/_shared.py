"""OpenAI 双 Strategy 共用的响应构造与默认值。"""

from __future__ import annotations

import json
from typing import NamedTuple

from lca.contracts.models.core.llm import LLMResponse, TokenUsage

DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 2048


class _RawToolCall(NamedTuple):
    name: str
    arguments_json: str
    call_id: str


def build_llm_response(
    *,
    text: str,
    tool_call: _RawToolCall | None,
    model: str,
    usage: TokenUsage | None,
) -> LLMResponse:
    """两 Strategy 的 complete() 尾部与 stream() 终态共用此构造函数。"""
    if tool_call is not None:
        text = json.dumps(
            {
                "action_type": "use_tool",
                "tool_name": tool_call.name,
                "arguments": json.loads(tool_call.arguments_json),
                "rationale": text or "",
            },
            ensure_ascii=False,
        )
    return LLMResponse(text=text, model=model, usage=usage)


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
