"""Anthropic 真实厂商适配器骨架（需网络与 API Key）。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from lca.contracts.protocols import LLMAdapter


class AnthropicLLMAdapter(LLMAdapter):
    """Anthropic Claude 适配器骨架。

    接口签名与 ``MockLLMAdapter`` / ``OpenAICompatAdapter`` 完全一致，
    Brain 层无需感知差异。生产环境需安装 ``anthropic`` SDK 并配置
    ``ANTHROPIC_API_KEY`` 环境变量后方可使用。
    """

    name = "anthropic"

    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        self.model = model

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        """占位实现：需要安装 anthropic SDK 并配置 API Key 后才能使用。"""
        raise NotImplementedError(
            "Anthropic 适配器需要安装 anthropic SDK 并配置 ANTHROPIC_API_KEY 环境变量"
        )

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[str]:
        raise NotImplementedError("示例中未实际联网调用，接口保留以展示L0可替换性")
        yield ""  # pragma: no cover
