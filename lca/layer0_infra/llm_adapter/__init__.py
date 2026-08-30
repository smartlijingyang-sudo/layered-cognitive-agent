"""L0 LLM 适配器 —— 统一多厂商模型调用。

``OpenAICompatAdapter`` 延迟导入以避免在无 ``openai`` SDK 的环境中触发 ImportError。
``MockLLMAdapter`` 和工厂函数无外部依赖，可直接导入。
"""

from __future__ import annotations

from typing import Any

from lca.layer0_infra.llm_adapter.api_style import LLMApiStyle
from lca.layer0_infra.llm_adapter.factory import load_dotenv_if_present, resolve_llm_adapter
from lca.layer0_infra.llm_adapter.failover import (
    FailoverLLMAdapter,
    LLMFailoverCandidate,
    LLMRetryPolicy,
    RetryingLLMAdapter,
)
from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter
from lca.layer0_infra.llm_adapter.settings import (
    LLMSettings,
    clear_llm_settings_cache,
    get_llm_settings,
)

__all__ = [
    "FailoverLLMAdapter",
    "LLMApiStyle",
    "LLMFailoverCandidate",
    "LLMRetryPolicy",
    "LLMSettings",
    "MockLLMAdapter",
    "OpenAICompatAdapter",
    "RetryingLLMAdapter",
    "clear_llm_settings_cache",
    "get_llm_settings",
    "load_dotenv_if_present",
    "resolve_llm_adapter",
]


def __getattr__(name: str) -> Any:
    if name == "OpenAICompatAdapter":
        from lca.layer0_infra.llm_adapter.openai_compat import OpenAICompatAdapter

        return OpenAICompatAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
