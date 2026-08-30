"""LLM resolver interface and provider-resolution tests."""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, cast

from lca.infrastructure.llm_resolver import ProductionLLMResolver

if TYPE_CHECKING:
    from lca.infrastructure.capability.llm import LlmService


class _Providers:
    def __init__(self, adapter: object) -> None:
        self._adapter = adapter

    def names(self) -> tuple[str, ...]:
        return ("primary",)

    def current(self) -> object:
        return self._adapter


class _LlmService:
    def __init__(self, adapter: object) -> None:
        self.providers = _Providers(adapter)


def test_resolver_interface_does_not_accept_run_mode() -> None:
    """Run-mode selection belongs to the gateway registry, never the LLM seam."""

    assert "mode" not in inspect.signature(ProductionLLMResolver).parameters
    assert "mode" not in inspect.signature(ProductionLLMResolver.resolve).parameters


def test_resolver_uses_active_provider_without_credentials() -> None:
    """A configured LLM provider is sufficient; credentials stay provider-owned."""

    adapter = object()
    resolver = ProductionLLMResolver(llm_service=cast("LlmService", _LlmService(adapter)))

    assert resolver.resolve() is adapter
