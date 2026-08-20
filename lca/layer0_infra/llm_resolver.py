"""LLM resolver — ``ProductionLLMResolver`` plus re-exports for backward compat.

The plugin (``lca.plugins.llm_resolver``) is the only thing that reads
credentials and wires an adapter. Two boots → two resolver instances;
no module-level singleton. The other names re-exported below live in
:mod:`lca.layer0_infra.llm`; the facade is kept so callers don't have
to know the real location.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

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

if TYPE_CHECKING:
    from lca.layer0_infra.capability.llm import LlmService


class ProductionLLMResolver:
    """Resolve an LLMAdapter for one run. Owns nothing but the policy.

    Production code constructs this with explicit kwargs (the
    ``lca-llm-resolver`` plugin does the env lookup and hands them in).
    Tests that just want ``is_available()`` may call without arguments.
    """

    def __init__(
        self,
        *,
        mode: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        default_model: str | None = None,
        llm_service: LlmService | None = None,
    ) -> None:
        self._mode = (mode or "auto").strip().lower()
        self._api_key = api_key
        self._base_url = base_url
        self._default_model = default_model or "deepseek-chat"
        # Held only for diagnostics / `is_available`; never read on resolve.
        self._llm_service = llm_service

    def is_available(self) -> bool:
        """True when the configured mode can produce a real adapter."""
        if self._mode == "mock":
            return True
        return bool(self._api_key)

    def resolve(self, *, mode: str | None = None) -> LLMAdapter:
        """Construct the adapter for the requested mode (overrides config)."""
        target = (mode or self._mode).strip().lower()
        if target == "mock" or not self._api_key:
            from lca.layer0_infra.llm_adapter.mock_llm import MockLLMAdapter

            return MockLLMAdapter()
        from lca.layer0_infra.llm_adapter.openai_compat import OpenAICompatAdapter

        return OpenAICompatAdapter(
            api_key=self._api_key,
            base_url=self._base_url,
            model=self._default_model,
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
    "llm_credentials",
    "llm_openai_credentials",
    "reset_async_openai_client",
    "resolve_llm_adapter",
]
