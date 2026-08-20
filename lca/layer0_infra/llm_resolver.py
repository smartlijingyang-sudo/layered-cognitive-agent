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


_LLM_MODES = frozenset({"auto", "mock", "real", "deepseek"})


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
    """Resolve an LLMAdapter for one run. Owns credentials and mode.

    The ``lca-llm-resolver`` plugin reads env, registers adapters on the
    llm service, and hands this resolver the same table. ``resolve()``
    returns the service's current adapter — it does not construct a
    second family of adapters.
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
        self._api_key = live_credential(api_key)
        self._base_url = live_credential(base_url)
        self._default_model = default_model or "deepseek-chat"
        self._llm_service = llm_service

    def is_available(self) -> bool:
        """True when the configured mode can produce a real adapter."""
        if self._mode == "mock":
            return True
        return bool(self._api_key)

    def resolve(self, *, mode: str | None = None) -> LLMAdapter:
        """Return the llm-service adapter for the configured LLM mode.

        *mode* is an LLM mode (``auto|mock|real|deepseek``). Gateway run
        modes such as ``solo`` are ignored so they cannot select a provider.
        """
        requested = (mode or "").strip().lower()
        target = requested if requested in _LLM_MODES else self._mode
        if target == "auto":
            target = "real" if self._api_key else "mock"
        if self._llm_service is not None:
            names = set(self._llm_service.providers.names())
            if target in names:
                return self._llm_service.providers.get(target)
            return self._llm_service.providers.current()
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
    "live_credential",
    "llm_credentials",
    "llm_openai_credentials",
    "reset_async_openai_client",
    "resolve_llm_adapter",
]
