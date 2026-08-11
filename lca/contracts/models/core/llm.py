"""LLM 调用结果契约 —— 结构化返回（文本 + 模型 + token 用量）。

可观测性的成本/用量链路以此为单一事实源：适配器返回 ``LLMResponse``，
观测装饰器将 usage 写入 span 属性，后端（如 Langfuse）据此自动计价。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lca.contracts.atoms.enums import LLMStreamEventType


@dataclass(frozen=True)
class TokenUsage:
    """Token 用量；字段为 None 表示 provider 未返回对应计数。"""

    prompt_tokens: int | None = None
    completion_tokens: int | None = None


@dataclass(frozen=True)
class NativeToolCall:
    """OpenAI 原生 function calling 返回的工具调用。

    直接透传 API 的 ``tool_calls`` 字段，不做任何编解码。
    """

    call_id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class LLMResponse:
    """单次 LLM 调用的结构化结果。

    ``text`` 为生成文本（``message.content``）；``tool_calls`` 为原生工具调用
    （``message.tool_calls``）。两者互斥：有 tool_calls 时 text 通常为空，
    但部分 provider 可能同时返回两者。
    ``model`` 为实际响应模型（可能异于请求模型）；
    ``usage`` 缺省 None（流式或 provider 不支持时）。
    ``finish_reason`` 为归一化结束原因。
    """

    text: str
    model: str = ""
    usage: TokenUsage | None = None
    finish_reason: str | None = None
    tool_calls: list[NativeToolCall] = field(default_factory=list)


@dataclass(frozen=True)
class LLMStreamEvent:
    """单次 LLM 流式调用的结构化事件。

    ``COMPLETED`` 事件的 ``response`` 与同次 ``complete()`` 返回值逐字段相等（不变式）。
    """

    type: LLMStreamEventType
    text: str = ""
    tool_call_id: str | None = None
    tool_name: str | None = None
    arguments_delta: str = ""
    response: LLMResponse | None = None
    extra: dict[str, Any] = field(default_factory=dict)
