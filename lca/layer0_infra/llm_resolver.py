"""LLM 解析门面 —— 保持既有 import 路径。

实现拆在 ``lca.layer0_infra.llm``：config（身份）、catalog（路由）、
openai_client（管家客户端）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from lca.contracts.protocols import LLMAdapter
from lca.layer0_infra.llm.catalog import (
    CHAT,
    EMBEDDINGS,
    MODEL_CATALOG,
    STREAMING,
    STRUCTURED_OUTPUT,
    TOOL_CALLING,
    VISION,
    ModelDefinition,
    ModelRegistry,
    get_model_registry,
)
from lca.layer0_infra.llm.config import llm_credentials, llm_openai_credentials
from lca.layer0_infra.llm.openai_client import (
    LLMUnavailableError,
    get_async_openai_client,
    reset_async_openai_client,
)
from lca.layer0_infra.llm_adapter import resolve_llm_adapter


class LLMResolver(Protocol):
    """解析一次 run 使用的 LLM adapter。"""

    def is_available(self) -> bool:
        """当前 resolver 是否可接受新的 run 请求。"""
        ...

    def resolve(self, *, mode: str) -> LLMAdapter:
        """为指定协作模式解析 LLM adapter。"""
        ...


@dataclass(frozen=True)
class ProductionLLMResolver:
    """生产 resolver：仅使用真实 LLM adapter，无静默降级。"""

    def is_available(self) -> bool:
        key, _, _ = llm_credentials()
        return bool(key)

    def resolve(self, *, mode: str) -> LLMAdapter:
        del mode
        key, base, model = llm_credentials()
        if not key:
            raise LLMUnavailableError("LLM_API_KEY 未配置。请设置环境变量或在 .env 中提供凭证。")
        return resolve_llm_adapter(api_key=key, base_url=base, model=model)


__all__ = [
    "CHAT",
    "EMBEDDINGS",
    "MODEL_CATALOG",
    "STREAMING",
    "STRUCTURED_OUTPUT",
    "TOOL_CALLING",
    "VISION",
    "LLMResolver",
    "LLMUnavailableError",
    "ModelDefinition",
    "ModelRegistry",
    "ProductionLLMResolver",
    "get_async_openai_client",
    "get_model_registry",
    "llm_credentials",
    "llm_openai_credentials",
    "reset_async_openai_client",
]
