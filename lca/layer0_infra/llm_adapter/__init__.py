"""L0 LLM 适配器 —— 统一多厂商模型调用。"""

from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter

__all__ = ["AnthropicLLMAdapter", "MockLLMAdapter", "OpenAICompatAdapter"]


from typing import Any


def __getattr__(name: str) -> Any:
    if name == "AnthropicLLMAdapter":
        from lca.layer0_infra.llm_adapter.anthropic_llm import AnthropicLLMAdapter

        return AnthropicLLMAdapter
    if name == "OpenAICompatAdapter":
        from lca.layer0_infra.llm_adapter.openai_compat import OpenAICompatAdapter

        return OpenAICompatAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
