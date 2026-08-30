"""Static model catalog and alias routing. Model id comes from provider config."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Final

from lca.infrastructure.llm.config import load_provider_settings
from lca.infrastructure.llm_adapter.factory import load_dotenv_if_present

CHAT: Final = "chat"
EMBEDDINGS: Final = "embeddings"
STRUCTURED_OUTPUT: Final = "structured_output"
VISION: Final = "vision"
TOOL_CALLING: Final = "tool_calling"
STREAMING: Final = "streaming"

_DEFAULT_EMBEDDING_MODEL: Final[str] = "text-embedding-v3"
_LCA_MODE_NAMES: Final[frozenset[str]] = frozenset({"solo", "team", "auto"})


@dataclass(frozen=True)
class ModelDefinition:
    """一种模型的静态元数据。"""

    id: str
    display_name: str
    provider: str
    capabilities: frozenset[str]
    context_window: int = 131_072
    max_output_tokens: int = 8192


_QWEN_CHAT_CAPS: frozenset[str] = frozenset(
    {CHAT, STRUCTURED_OUTPUT, VISION, TOOL_CALLING, STREAMING}
)

_KNOWN_MODELS: tuple[ModelDefinition, ...] = (
    ModelDefinition("qwen3.7-plus", "Qwen 3.7 Plus", "dashscope", _QWEN_CHAT_CAPS),
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

MODEL_CATALOG: Final[dict[str, ModelDefinition]] = {item.id: item for item in _KNOWN_MODELS}

_OPENAI_EMBEDDING_ALIASES: Final[dict[str, str]] = {
    "text-embedding-3-small": "text-embedding-v3",
    "text-embedding-3-large": "text-embedding-v3",
    "text-embedding-ada-002": "text-embedding-v2",
}

_OPENAI_CHAT_ALIASES: Final[dict[str, str]] = {
    "gpt-4o": "qwen-max",
    "gpt-4o-mini": "qwen-plus",
    "gpt-4-turbo": "qwen-max",
    "gpt-3.5-turbo": "qwen-turbo",
}


class ModelRegistry:
    """模型路由与能力查询。Chat model 只读 provider config。"""

    def __init__(self) -> None:
        self._configured_embedding_model: str | None = None

    @property
    def configured_chat_model(self) -> str:
        return load_provider_settings().configured_model()

    @property
    def configured_embedding_model(self) -> str:
        if self._configured_embedding_model is None:
            load_dotenv_if_present()
            settings = load_provider_settings()
            override = settings.embedding_model.strip()
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
        self._configured_embedding_model = None


@lru_cache(maxsize=1)
def get_model_registry() -> ModelRegistry:
    return ModelRegistry()
