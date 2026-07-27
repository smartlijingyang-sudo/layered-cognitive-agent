"""Anthropic 真实厂商适配器骨架（需网络与 API Key）。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from lca.contracts.protocols import LLMAdapter


class AnthropicLLMAdapter(LLMAdapter):
    """
    真实厂商适配器示例。接口签名与 MockLLMAdapter 完全一致，
    Brain 层无需感知差异。生产环境取消注释即可使用。
    """

    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        self.model = model

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        # from anthropic import AsyncAnthropic
        # client = AsyncAnthropic()
        # resp = await client.messages.create(
        #     model=self.model, max_tokens=1000,
        #     messages=[{"role": "user", "content": prompt}],
        # )
        # return resp.content[0].text
        raise NotImplementedError("示例中未实际联网调用，接口保留以展示L0可替换性")

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[str]:
        raise NotImplementedError("示例中未实际联网调用，接口保留以展示L0可替换性")
        yield ""  # pragma: no cover
