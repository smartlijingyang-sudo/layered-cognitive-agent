"""LLM resolver — ``ProductionLLMResolver`` plus LLM infrastructure exports.

The plugin (``lca.plugins.seam_definitions.llm_resolver``) is the only thing that loads
``.env``, normalizes aliases, and wires the chat adapter. No product
``mode`` vocabulary (mock / deepseek / auto).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lca.contracts.protocols import LLMAdapter
from lca.infrastructure.llm.catalog import (
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
from lca.infrastructure.llm.config import (
    DEFAULT_CHAT_MODEL,
    llm_credentials,
    llm_openai_credentials,
)
from lca.infrastructure.llm.openai_client import (
    LLMUnavailableError,
    get_async_openai_client,
    reset_async_openai_client,
)
from lca.infrastructure.llm_adapter import resolve_llm_adapter

if TYPE_CHECKING:
    from lca.infrastructure.capability.llm import LlmService


def live_credential(value: str | None) -> str | None:
    """Treat empty strings and unresolved ``${ENV}`` placeholders as no secret."""
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    if text.startswith("${") and text.endswith("}"):
        return None
    return text


class ProductionLLMResolver:
    """Resolve the chat LLMAdapter for one run. Owns credentials after boot.

    ``resolve()`` returns the llm-service's active adapter when the plugin
    registered one; otherwise constructs an OpenAI-compat adapter from the
    stored credentials. Never silently falls back to Mock.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        openai_base_url: str | None = None,
        default_model: str | None = None,
        api_style: str | None = None,
        llm_service: LlmService | None = None,
    ) -> None:
        self._api_key = live_credential(api_key)
        self._base_url = live_credential(base_url)
        self._openai_base_url = live_credential(openai_base_url)
        self._default_model = (default_model or "").strip() or DEFAULT_CHAT_MODEL
        self._api_style = (api_style or "").strip() or None
        self._llm_service = llm_service

    def is_available(self) -> bool:
        return bool(self._api_key)

    def resolve(self) -> LLMAdapter:
        """Return the registered chat adapter, or build one from credentials."""
        if self._llm_service is not None:
            names = set(self._llm_service.providers.names())
            if names:
                return self._llm_service.providers.current()
        if not self._api_key:
            raise LLMUnavailableError("LLM_API_KEY 未配置，无法解析 chat adapter")
        from lca.infrastructure.llm_adapter.api_style import LLMApiStyle
        from lca.infrastructure.llm_adapter.openai_compat import OpenAICompatAdapter

        style = None
        if self._api_style:
            for candidate in LLMApiStyle:
                if candidate.value == self._api_style or candidate.name.lower() == self._api_style:
                    style = candidate
                    break
        return OpenAICompatAdapter(
            api_key=self._api_key,
            base_url=self._base_url,
            model=self._default_model,
            api=style,
        )


__all__ = [
    "CHAT",
    "EMBEDDINGS",
    "MODEL_CATALOG",
    "STREAMING",
    "STRUCTURED_OUTPUT",
    "TOOL_CALLING",
    "VISION",
    "LLMUnavailableError",
    "ModelDefinition",
    "ModelRegistry",
    "ProductionLLMResolver",
    "get_async_openai_client",
    "get_model_registry",
    "live_credential",
    "llm_credentials",
    "llm_openai_credentials",
    "reset_async_openai_client",
    "resolve_llm_adapter",
]
