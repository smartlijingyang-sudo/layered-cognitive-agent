"""LLM 基础设施 —— adapter 工厂 + 模型路由 + 能力目录。

统一职责：
  1. LLM Adapter 工厂 —— env 凭证 → LLMAdapter（ProductionLLMResolver）
  2. 模型路由 —— OpenAI 模型名 / LCA 模式名 → 实际上游模型 ID（ModelRegistry）
  3. 能力目录 —— 已知模型 → 能力映射（MODEL_CATALOG）
  4. 管家客户端 —— ``LLM_OPENAI_BASE_URL`` 上的 AsyncOpenAI（get_async_openai_client）
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Final, Protocol

from lca.contracts.protocols import LLMAdapter
from lca.layer0_infra.llm_adapter import load_dotenv_if_present, resolve_llm_adapter

# ═══════════════════════════════════════════════════════════
#  LLM Adapter 工厂
# ═══════════════════════════════════════════════════════════


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
    """Agent 口：``LLM_BASE_URL`` + ``LLM_API_STYLE``（可以是 Anthropic Messages）。"""
    load_dotenv_if_present()
    key = os.getenv("LLM_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")
    base = os.getenv("LLM_BASE_URL") or os.getenv("ANTHROPIC_BASE_URL")
    model = os.getenv("LLM_MODEL") or os.getenv("ANTHROPIC_MODEL")
    return key, base, model


def llm_openai_credentials() -> tuple[str | None, str | None, str | None]:
    """管家口：必须是 OpenAI 兼容 base。禁止复用 Anthropic Messages URL。"""
    key, agent_base, model = llm_credentials()
    openai_base = (os.getenv("LLM_OPENAI_BASE_URL") or "").strip() or None
    if openai_base:
        return key, openai_base, model
    from lca.layer0_infra.llm_adapter.openai_compat._anthropic_messages import (
        looks_like_anthropic_base_url,
    )

    if looks_like_anthropic_base_url(agent_base):
        return key, None, model
    return key, agent_base, model


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
    """管家面客户端：只打 OpenAI 兼容口，不打 agent 的 Anthropic Messages 口。"""
    global _cached_async_client, _cached_client_key
    key, base, _ = llm_openai_credentials()
    if not base:
        raise LLMUnavailableError(
            "LLM_OPENAI_BASE_URL 未配置。管家面（标题 / generateObject / embeddings）"
            "需要 OpenAI 兼容口；agent 的 LLM_BASE_URL 是 Anthropic Messages，"
            "不能拼 /chat/completions。"
        )
    cache_key = (key, base)
    if _cached_async_client is not None and _cached_client_key == cache_key:
        return _cached_async_client
    from openai import AsyncOpenAI

    _cached_async_client = AsyncOpenAI(api_key=key, base_url=base)
    _cached_client_key = cache_key
    return _cached_async_client


def reset_async_openai_client() -> None:
    """测试用：丢掉缓存的管家客户端。"""
    global _cached_async_client, _cached_client_key
    _cached_async_client = None
    _cached_client_key = None


# ═══════════════════════════════════════════════════════════
#  模型能力目录 + 路由
# ═══════════════════════════════════════════════════════════

# ── 能力词表 ────────────────────────────────────────────────

CHAT: Final = "chat"
EMBEDDINGS: Final = "embeddings"
STRUCTURED_OUTPUT: Final = "structured_output"
VISION: Final = "vision"
TOOL_CALLING: Final = "tool_calling"
STREAMING: Final = "streaming"


@dataclass(frozen=True)
class ModelDefinition:
    """一种模型的静态元数据。"""

    id: str
    display_name: str
    provider: str
    capabilities: frozenset[str]
    context_window: int = 131_072
    max_output_tokens: int = 8192


# ── 静态模型目录 ────────────────────────────────────────────

_QWEN_CHAT_CAPS: frozenset[str] = frozenset(
    {CHAT, STRUCTURED_OUTPUT, VISION, TOOL_CALLING, STREAMING}
)

_KNOWN_MODELS: tuple[ModelDefinition, ...] = (
    ModelDefinition("qwen-plus", "Qwen Plus", "dashscope", _QWEN_CHAT_CAPS),
    ModelDefinition("qwen-turbo", "Qwen Turbo", "dashscope", _QWEN_CHAT_CAPS),
    ModelDefinition("qwen-max", "Qwen Max", "dashscope", _QWEN_CHAT_CAPS),
    ModelDefinition(
        "qwen-long",
        "Qwen Long",
        "dashscope",
        frozenset({CHAT, STRUCTURED_OUTPUT, TOOL_CALLING, STREAMING}),
        context_window=1_000_000,
    ),
    ModelDefinition(
        "text-embedding-v3",
        "Text Embedding V3",
        "dashscope",
        frozenset({EMBEDDINGS}),
        context_window=8_192,
    ),
    ModelDefinition(
        "text-embedding-v2",
        "Text Embedding V2",
        "dashscope",
        frozenset({EMBEDDINGS}),
        context_window=2_048,
    ),
    ModelDefinition("gpt-4o", "GPT-4o (→ qwen-max)", "openai", _QWEN_CHAT_CAPS),
    ModelDefinition("gpt-4o-mini", "GPT-4o Mini (→ qwen-plus)", "openai", _QWEN_CHAT_CAPS),
)

MODEL_CATALOG: Final[dict[str, ModelDefinition]] = {}
for _def in _KNOWN_MODELS:
    MODEL_CATALOG[_def.id] = _def

# ── 别名映射 ────────────────────────────────────────────────

_OPENAI_EMBEDDING_ALIASES: Final[dict[str, str]] = {
    "text-embedding-3-small": "text-embedding-v3",
    "text-embedding-3-large": "text-embedding-v3",
    "text-embedding-ada-002": "text-embedding-v2",
}

_LCA_MODE_NAMES: Final[frozenset[str]] = frozenset({"solo", "team", "auto"})

_OPENAI_CHAT_ALIASES: Final[dict[str, str]] = {
    "gpt-4o": "qwen-max",
    "gpt-4o-mini": "qwen-plus",
    "gpt-4-turbo": "qwen-max",
    "gpt-3.5-turbo": "qwen-turbo",
}

_DEFAULT_CHAT_MODEL: Final[str] = "qwen-plus"
_DEFAULT_EMBEDDING_MODEL: Final[str] = "text-embedding-v3"


class ModelRegistry:
    """模型路由与能力查询。"""

    def __init__(self) -> None:
        self._configured_chat_model: str | None = None
        self._configured_embedding_model: str | None = None
        self._env_loaded: bool = False

    def _ensure_env(self) -> None:
        if not self._env_loaded:
            load_dotenv_if_present()
            self._env_loaded = True

    @property
    def configured_chat_model(self) -> str:
        if self._configured_chat_model is None:
            self._ensure_env()
            self._configured_chat_model = (
                os.getenv("LLM_MODEL") or os.getenv("ANTHROPIC_MODEL") or _DEFAULT_CHAT_MODEL
            ).strip() or _DEFAULT_CHAT_MODEL
        return self._configured_chat_model

    @property
    def configured_embedding_model(self) -> str:
        if self._configured_embedding_model is None:
            self._ensure_env()
            override = os.getenv("LLM_EMBEDDING_MODEL", "").strip()
            if override:
                self._configured_embedding_model = override
            else:
                self._configured_embedding_model = _OPENAI_EMBEDDING_ALIASES.get(
                    self.configured_chat_model.lower(), _DEFAULT_EMBEDDING_MODEL
                )
        return self._configured_embedding_model

    def resolve_chat_model(self, requested: str) -> str:
        """LCA 模式名 → configured；OpenAI 名 → Qwen 等价；其他 → 透传。"""
        normalized = requested.strip().lower()
        if normalized in _LCA_MODE_NAMES:
            return self.configured_chat_model
        return _OPENAI_CHAT_ALIASES.get(normalized, requested.strip() or self.configured_chat_model)

    def resolve_embedding_model(self, requested: str) -> str:
        normalized = requested.strip().lower()
        if normalized in _LCA_MODE_NAMES:
            return self.configured_embedding_model
        return _OPENAI_EMBEDDING_ALIASES.get(
            normalized, requested.strip() or _DEFAULT_EMBEDDING_MODEL
        )

    def is_lca_mode(self, model_id: str) -> bool:
        return model_id.strip().lower() in _LCA_MODE_NAMES

    def get_definition(self, model_id: str) -> ModelDefinition | None:
        return MODEL_CATALOG.get(model_id)

    def supports(self, model_id: str, capability: str) -> bool:
        defn = self.get_definition(model_id)
        if defn is None:
            return True
        return capability in defn.capabilities

    def list_available(self) -> list[ModelDefinition]:
        seen: set[str] = set()
        result: list[ModelDefinition] = []

        chat_model = self.configured_chat_model
        if chat_model not in seen:
            defn = self.get_definition(chat_model)
            if defn is not None:
                result.append(defn)
            else:
                result.append(
                    ModelDefinition(
                        id=chat_model,
                        display_name=chat_model,
                        provider="configured",
                        capabilities=_QWEN_CHAT_CAPS,
                    )
                )
            seen.add(chat_model)

        emb_model = self.configured_embedding_model
        if emb_model not in seen:
            defn = self.get_definition(emb_model)
            if defn is not None:
                result.append(defn)
            else:
                result.append(
                    ModelDefinition(
                        id=emb_model,
                        display_name=emb_model,
                        provider="configured",
                        capabilities=frozenset({EMBEDDINGS}),
                    )
                )
            seen.add(emb_model)

        return result

    def reset(self) -> None:
        self._configured_chat_model = None
        self._configured_embedding_model = None
        self._env_loaded = False


@lru_cache(maxsize=1)
def get_model_registry() -> ModelRegistry:
    """进程级单例。"""
    return ModelRegistry()
