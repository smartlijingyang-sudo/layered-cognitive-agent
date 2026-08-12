"""Gateway model provider registry —— 模型能力目录与路由单一事实源。

职责：
1. 静态目录 —— 已知模型 ID → 能力映射（``MODEL_CATALOG``）
2. 配置解析 —— 从环境变量解析当前部署使用的模型
3. 路由 —— LCA 模式名 / OpenAI 模型名 → 实际上游模型 ID
4. 能力查询 —— ``supports_chat`` / ``supports_embeddings`` / ``supports_structured``

替代原先散落在 ``openai_structured_llm.py`` 的硬编码别名 dict 与
``resolve_upstream_model`` / ``resolve_embedding_model`` 函数。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Final

from lca.layer0_infra.llm_adapter import load_dotenv_if_present

# ── 能力词表 ────────────────────────────────────────────────

CHAT: Final = "chat"
EMBEDDINGS: Final = "embeddings"
STRUCTURED_OUTPUT: Final = "structured_output"
VISION: Final = "vision"
TOOL_CALLING: Final = "tool_calling"
STREAMING: Final = "streaming"

# ── 模型定义 ────────────────────────────────────────────────


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

# 注册已知模型 —— 按 provider 分组，便于扩展
_KNOWN_MODELS: tuple[ModelDefinition, ...] = (
    # ── Qwen (DashScope / 百炼) ──
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
    # ── Qwen Embeddings ──
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
    # ── OpenAI 标准名 → 映射到 DashScope 等价 ──
    ModelDefinition(
        "gpt-4o",
        "GPT-4o (→ qwen-max)",
        "openai",
        _QWEN_CHAT_CAPS,
    ),
    ModelDefinition(
        "gpt-4o-mini",
        "GPT-4o Mini (→ qwen-plus)",
        "openai",
        _QWEN_CHAT_CAPS,
    ),
)

# 构建不可变目录
MODEL_CATALOG: Final[dict[str, ModelDefinition]] = {}
for _def in _KNOWN_MODELS:
    MODEL_CATALOG[_def.id] = _def

# ── OpenAI → DashScope 别名（嵌入模型）──────────────────────

_OPENAI_EMBEDDING_ALIASES: Final[dict[str, str]] = {
    "text-embedding-3-small": "text-embedding-v3",
    "text-embedding-3-large": "text-embedding-v3",
    "text-embedding-ada-002": "text-embedding-v2",
}

# LCA 模式名集合（这些不是真实模型，需要映射到配置模型）
_LCA_MODE_NAMES: Final[frozenset[str]] = frozenset({"solo", "team", "auto"})

# OpenAI 标准名 → Qwen 等价（chat 模型）
_OPENAI_CHAT_ALIASES: Final[dict[str, str]] = {
    "gpt-4o": "qwen-max",
    "gpt-4o-mini": "qwen-plus",
    "gpt-4-turbo": "qwen-max",
    "gpt-3.5-turbo": "qwen-turbo",
}

_DEFAULT_CHAT_MODEL: Final[str] = "qwen-plus"
_DEFAULT_EMBEDDING_MODEL: Final[str] = "text-embedding-v3"


# ── 注册表 ──────────────────────────────────────────────────


class ModelRegistry:
    """模型路由与能力查询。

    单一事实源：
    - ``/v1/models`` 端点从 ``list_available()`` 生成响应
    - ``/v1/chat/completions`` 通过 ``resolve_chat_model()`` 路由
    - ``/v1/embeddings`` 通过 ``resolve_embedding_model()`` 路由
    - ``/v1/responses`` 通过 ``resolve_chat_model()`` 路由

    延迟加载环境变量（首次调用时 ``load_dotenv``），避免模块导入副作用。
    """

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
        """当前部署的 chat 模型（``LLM_MODEL`` 环境变量或默认值）。"""
        if self._configured_chat_model is None:
            self._ensure_env()
            self._configured_chat_model = (
                os.getenv("LLM_MODEL") or os.getenv("ANTHROPIC_MODEL") or _DEFAULT_CHAT_MODEL
            ).strip() or _DEFAULT_CHAT_MODEL
        return self._configured_chat_model

    @property
    def configured_embedding_model(self) -> str:
        """当前部署的 embedding 模型（``LLM_EMBEDDING_MODEL`` 或从 chat 模型推断）。"""
        if self._configured_embedding_model is None:
            self._ensure_env()
            override = os.getenv("LLM_EMBEDDING_MODEL", "").strip()
            if override:
                self._configured_embedding_model = override
            else:
                self._configured_embedding_model = _OPENAI_EMBEDDING_ALIASES.get(
                    self.configured_chat_model.lower(),
                    _DEFAULT_EMBEDDING_MODEL,
                )
        return self._configured_embedding_model

    def resolve_chat_model(self, requested: str) -> str:
        """解析请求的模型名为实际上游 chat 模型 ID。

        规则：
        1. LCA 模式名（solo/team/auto）→ 返回 ``configured_chat_model``
        2. OpenAI 标准名（gpt-4o 等）→ 映射到 Qwen 等价
        3. 其他 → 原样透传（假设上游支持）
        """
        normalized = requested.strip().lower()
        if normalized in _LCA_MODE_NAMES:
            return self.configured_chat_model
        return _OPENAI_CHAT_ALIASES.get(normalized, requested.strip() or self.configured_chat_model)

    def resolve_embedding_model(self, requested: str) -> str:
        """解析请求的 embedding 模型名为实际上游模型 ID。"""
        normalized = requested.strip().lower()
        if normalized in _LCA_MODE_NAMES:
            return self.configured_embedding_model
        return _OPENAI_EMBEDDING_ALIASES.get(
            normalized, requested.strip() or _DEFAULT_EMBEDDING_MODEL
        )

    def is_lca_mode(self, model_id: str) -> bool:
        """模型 ID 是否为 LCA 模式名（非真实模型）。"""
        return model_id.strip().lower() in _LCA_MODE_NAMES

    def get_definition(self, model_id: str) -> ModelDefinition | None:
        """查找模型的静态定义（目录中有注册则返回）。"""
        return MODEL_CATALOG.get(model_id)

    def supports(self, model_id: str, capability: str) -> bool:
        """检查模型是否支持指定能力。未知模型保守返回 True（假设支持）。"""
        defn = self.get_definition(model_id)
        if defn is None:
            return True
        return capability in defn.capabilities

    def list_available(self) -> list[ModelDefinition]:
        """列出当前部署可用的模型（用于 ``/v1/models`` 响应）。

        包含：
        - 当前配置的 chat 模型
        - 当前配置的 embedding 模型
        - LCA 模式（solo/team）作为虚拟模型
        """
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
        """重置缓存的配置（测试用）。"""
        self._configured_chat_model = None
        self._configured_embedding_model = None
        self._env_loaded = False


@lru_cache(maxsize=1)
def get_model_registry() -> ModelRegistry:
    """进程级单例。"""
    return ModelRegistry()



