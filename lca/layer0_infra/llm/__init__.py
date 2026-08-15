"""LLM provider configuration and catalog.

Adapters live in ``llm_adapter``. This package owns *who* we call
(identity + faces), not *how* a request is encoded.
"""

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
from lca.layer0_infra.llm.config import (
    DEFAULT_CHAT_MODEL,
    LLMFace,
    LLMProviderSettings,
    ResolvedEndpoint,
    configured_chat_model,
    llm_credentials,
    llm_openai_credentials,
    load_provider_settings,
    resolve_endpoint,
)
from lca.layer0_infra.llm.openai_client import (
    LLMUnavailableError,
    get_async_openai_client,
    reset_async_openai_client,
)

__all__ = [
    "CHAT",
    "DEFAULT_CHAT_MODEL",
    "EMBEDDINGS",
    "MODEL_CATALOG",
    "STREAMING",
    "STRUCTURED_OUTPUT",
    "TOOL_CALLING",
    "VISION",
    "LLMFace",
    "LLMProviderSettings",
    "LLMUnavailableError",
    "ModelDefinition",
    "ModelRegistry",
    "ResolvedEndpoint",
    "configured_chat_model",
    "get_async_openai_client",
    "get_model_registry",
    "llm_credentials",
    "llm_openai_credentials",
    "load_provider_settings",
    "reset_async_openai_client",
    "resolve_endpoint",
]
