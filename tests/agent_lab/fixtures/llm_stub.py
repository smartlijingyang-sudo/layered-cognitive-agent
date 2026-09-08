"""LLM adapter stub used by agent_lab tests.

A minimal ``lca.contracts.protocols.runtime.infra.infra.LLMAdapter``
implementation that returns a fixed ``LLMResponse``. Used by
``test_think_subgraph_runs_via_runner`` to exercise the think pipeline
end-to-end without an actual LLM provider or network access.

Importable as ``tests.agent_lab.fixtures.llm_stub:StubLlmAdapter``.
"""

from __future__ import annotations

from typing import Any


class StubLlmAdapter:
    """Returns a constant LLMResponse from any prompt."""

    text: str = "stub-llm-response"
    model: str = "stub-llm"

    async def complete(self, prompt: str, **kwargs: Any) -> Any:  # type: ignore[no-untyped-def]
        from lca.contracts.models.core.conversation.llm import LLMResponse

        return LLMResponse(text=self.text, model=self.model, tool_calls=[])
