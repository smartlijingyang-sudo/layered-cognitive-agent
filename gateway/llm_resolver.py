"""Gateway LLM 解析 —— 生产路径只认真实 adapter；测试通过依赖注入替换。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol

from lca.contracts.protocols import LLMAdapter
from lca.layer0_infra.llm_adapter import load_dotenv_if_present, resolve_llm_adapter


class LLMUnavailableError(RuntimeError):
    """LLM 凭证缺失，无法创建 run。"""


class LLMResolver(Protocol):
    """解析一次 run 使用的 LLM adapter。"""

    def is_available(self) -> bool:
        """当前 resolver 是否可接受新的 run 请求。"""
        ...

    def resolve(self, *, mode: str) -> LLMAdapter:
        """为指定协作模式解析 LLM adapter。"""
        ...


def llm_credentials() -> tuple[str | None, str | None, str | None]:
    """LLM_API_KEY 优先；兼容 CCS / Cursor 注入的 ANTHROPIC_* 变量。"""
    load_dotenv_if_present()
    key = os.getenv("LLM_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")
    base = os.getenv("LLM_BASE_URL") or os.getenv("ANTHROPIC_BASE_URL")
    model = os.getenv("LLM_MODEL") or os.getenv("ANTHROPIC_MODEL")
    return key, base, model


@dataclass(frozen=True)
class ProductionLLMResolver:
    """生产 resolver：仅使用真实 LLM adapter，无静默降级。"""

    def is_available(self) -> bool:
        key, _, _ = llm_credentials()
        return bool(key)

    def resolve(self, *, mode: str) -> LLMAdapter:
        del mode  # 生产路径与模式无关，保留签名便于测试替身
        key, base, model = llm_credentials()
        if not key:
            raise LLMUnavailableError("LLM_API_KEY 未配置。请设置环境变量或在 .env 中提供凭证。")
        return resolve_llm_adapter(api_key=key, base_url=base, model=model)


# ── 共享异步客户端工厂 ──────────────────────────────────────

_cached_async_client: Any = None
_cached_client_key: tuple[str | None, str | None] | None = None


def get_async_openai_client() -> Any:
    """返回缓存的 ``AsyncOpenAI`` 客户端（按 credentials 去重）。

    消除 ``openai_structured_llm.py`` 与各适配器重复创建客户端的问题。
    延迟导入 ``openai`` SDK，避免无该依赖的环境 ImportError。
    """
    global _cached_async_client, _cached_client_key
    key, base, _ = llm_credentials()
    cache_key = (key, base)
    if _cached_async_client is not None and _cached_client_key == cache_key:
        return _cached_async_client
    from openai import AsyncOpenAI

    _cached_async_client = AsyncOpenAI(api_key=key, base_url=base)
    _cached_client_key = cache_key
    return _cached_async_client



