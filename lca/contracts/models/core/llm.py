"""LLM 调用结果契约 —— 结构化返回（文本 + 模型 + token 用量）。

可观测性的成本/用量链路以此为单一事实源：适配器返回 ``LLMResponse``，
观测装饰器将 usage 写入 span 属性，后端（如 Langfuse）据此自动计价。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TokenUsage:
    """Token 用量；字段为 None 表示 provider 未返回对应计数。"""

    prompt_tokens: int | None = None
    completion_tokens: int | None = None


@dataclass(frozen=True)
class LLMResponse:
    """单次 LLM 调用的结构化结果。

    ``text`` 为生成文本；``model`` 为实际响应模型（可能异于请求模型）；
    ``usage`` 缺省 None（流式或 provider 不支持时）。
    """

    text: str
    model: str = ""
    usage: TokenUsage | None = None
