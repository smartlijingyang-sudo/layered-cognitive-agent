"""Adapter: agent_lab call_llm node ↔ LCA LLMAdapter Protocol.

LCA contracts consumed (read-only):
  - lca.contracts.protocols.runtime.infra.infra.LLMAdapter  (async complete Protocol)
  - lca.contracts.models.core.conversation.llm.LLMResponse

agent_lab provides (this file):
  - LlmAdapterShim: implements LCA's LLMAdapter Protocol by wrapping a
    sync callable(messages) -> str.
  - LcaLlmProvider: wraps a LlmAdapterShim into agent_lab's provider
    interface so call_llm node can dispatch via register_llm_provider().
"""

from __future__ import annotations

from typing import Any

from agent_lab.primitives.artifact import Artifact, ArtifactKind, make_message


class LlmAdapterShim:
    """Satisfies LCA's LLMAdapter Protocol; backing callable is sync.

    Uses minimal no-op implementation of ``stream`` (yields a single
    COMPLETED event). The body of ``complete`` adapts agent_lab's
    message list back into a single prompt string.
    """

    def __init__(self, callable_: callable) -> None:
        self._callable = callable_
        self.model: str = "agent-lab-shim"

    async def complete(self, prompt: str, **kwargs: Any):
        # Lazy import to keep agent_lab bootable without lca.
        from lca.contracts.models.core.conversation.llm import LLMResponse

        text = self._callable(prompt, **kwargs)
        return LLMResponse(text=text, model=self.model)

    async def stream(self, prompt: str, **kwargs: Any):
        from lca.contracts.models.core.conversation.llm import (
            LLMResponse,
            LLMStreamEvent,
        )
        from lca.contracts.models.core.conversation.llm import (
            LLMStreamEventType as T,
        )

        text = self._callable(prompt, **kwargs)
        yield LLMStreamEvent(type=T.OUTPUT_TEXT_DELTA, text=text)
        yield LLMStreamEvent(type=T.COMPLETED, response=LLMResponse(text=text, model=self.model))


class LcaLlmProvider:
    """Bridge agent_lab call_llm node to LCA LLMAdapter."""

    def __init__(self, adapter: LlmAdapterShim) -> None:
        self._adapter = adapter

    def complete(
        self,
        *,
        messages_artifact: Artifact | None,
    ) -> Artifact:
        messages = messages_artifact.content if messages_artifact is not None else []
        if not isinstance(messages, list):
            messages = [{"role": "user", "content": str(messages)}]
        prompt = self._flatten(messages)
        # asyncio-free adapter invocation: the shim is async internally but
        # we run it via asyncio.run for a single round-trip.
        import asyncio

        response = asyncio.run(self._adapter.complete(prompt))
        return make_message(response.text or "assistant", content=response.text)

    @staticmethod
    def _flatten(messages: list[dict]) -> str:
        parts: list[str] = []
        for m in messages:
            if not isinstance(m, dict):
                continue
            role = m.get("role", "user")
            content = m.get("content", "")
            parts.append(f"[{role}] {content}")
        return "\n".join(parts)


def make_message_artifact(content: str, role: str = "assistant") -> Artifact:
    return Artifact(
        kind=ArtifactKind.MESSAGE,
        content={"role": role, "content": content},
        schema_ref="openai.message.v1",
    )
