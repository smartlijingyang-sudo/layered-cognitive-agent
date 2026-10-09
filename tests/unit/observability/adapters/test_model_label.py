"""Unit tests for ``_model_label`` — model identity comes from the declared accessor.

RA-106: ``LLMAdapter.model_name`` is now part of the protocol; telemetry must
not probe a private ``_model`` attribute. These tests pin the declared-accessor
path and the fallback for adapters without a model identity.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from lca.contracts.atoms.enums.enums import LLMStreamEventType
from lca.contracts.models.core.conversation.llm import (
    LLMResponse,
    LLMStreamEvent,
    TokenUsage,
)
from lca.contracts.protocols import LLMAdapter
from lca.infrastructure.llm_adapter import MockLLMAdapter
from lca.infrastructure.llm_adapter.api.style import LLMApiStyle
from lca.infrastructure.llm_adapter.model_override import ModelOverridingLLMAdapter
from lca.infrastructure.llm_adapter.openai_compat import OpenAICompatAdapter
from lca.infrastructure.observability.adapters import adapters as _adapter_mod


class _ProtocolOnlyAdapter(LLMAdapter):
    """Implements the protocol but stores its model under a non-``_model`` name."""

    name = "protocol-only"

    def __init__(self) -> None:
        self.model_id = "declared-model-42"

    @property
    def model_name(self) -> str:
        return self.model_id

    async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        return LLMResponse(text="", model=self.model_id, usage=TokenUsage())

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[LLMStreamEvent]:
        yield LLMStreamEvent(type=LLMStreamEventType.COMPLETED)


def test_model_label_uses_declared_accessor_without_model_attr() -> None:
    """A protocol-only adapter (no ``_model``) yields its declared model id."""
    assert _adapter_mod._model_label(_ProtocolOnlyAdapter()) == "declared-model-42"


def test_model_label_mock_returns_mock_llm() -> None:
    """``MockLLMAdapter`` declares ``model_name == 'mock-llm'``."""
    assert _adapter_mod._model_label(MockLLMAdapter()) == "mock-llm"


def test_model_label_openai_compat_returns_configured_model() -> None:
    """``OpenAICompatAdapter`` (incl. Anthropic style) returns its configured model."""
    adapter = OpenAICompatAdapter(model="qwen-max", api_key="sk-test", api=LLMApiStyle.ANTHROPIC)
    assert adapter.model_name == "qwen-max"
    assert _adapter_mod._model_label(adapter) == "qwen-max"


def test_model_label_model_override_returns_assistant_model() -> None:
    """``ModelOverridingLLMAdapter`` labels with the assistant-selected model."""
    override = ModelOverridingLLMAdapter(inner=_ProtocolOnlyAdapter(), model="assistant-model")
    assert _adapter_mod._model_label(override) == "assistant-model"


def test_model_label_falls_back_to_name_when_model_name_unimplemented() -> None:
    """A wrapper that does not declare a model identity falls back to ``name``."""

    class _Wrapper(LLMAdapter):
        name = "wrapper-no-model"

        async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
            return LLMResponse(text="", model="", usage=TokenUsage())

        async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[LLMStreamEvent]:
            yield LLMStreamEvent(type=LLMStreamEventType.COMPLETED)

    assert _adapter_mod._model_label(_Wrapper()) == "wrapper-no-model"
