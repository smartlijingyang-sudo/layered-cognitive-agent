"""Public exports for ``chat`` (auto-fixed)."""

from lca.infrastructure.llm_adapter.openai_compat.chat._chat_completions import (
    to_openai_chat_tool_spec,
)

__all__ = ['to_openai_chat_tool_spec']
