"""Adapter: agent_lab call_llm node ↔ LCA LLMAdapter Protocol.

LCA contracts consumed (read-only):
  - lca.contracts.protocols.runtime.infra.infra.LLMAdapter  (async complete Protocol)
  - lca.contracts.models.core.conversation.llm.LLMResponse

agent_lab provides (this file):
  - LcaLlmProvider: wraps any ``lca.contracts.protocols.LLMAdapter`` into
    agent_lab's provider interface so a ``call_llm`` node can dispatch
    via ``provider_ref``. The wrapper is a thin bridge from agent_lab's
    ``Artifact`` contract to the adapter's ``prompt: str`` contract.

YAML declares a provider via ``adapter_factory: {ref, kwargs}``. The
``ref`` resolves to a class implementing ``LLMAdapter`` (e.g.
``lca.infrastructure.llm_adapter.openai_compat:OpenAICompatAdapter``).
The default factory for ``provider_kind: lca`` is this ``LcaLlmProvider``
itself; in production graphs you usually point it at
``OpenAICompatAdapter`` directly.
"""

from __future__ import annotations

import asyncio
import importlib
from typing import Any

from agent_lab.primitives.artifact import Artifact, ArtifactKind, make_message


class LcaLlmProvider:
    """Bridge agent_lab call_llm node to a real LCA LLMAdapter.

    Accepts either a pre-built ``LLMAdapter`` (``adapter=``) or a factory
    reference dict (``adapter_factory=``) shaped like
    ``{"ref": "module:Class", "kwargs": {...}}``. The latter lets YAML
    config fully describe the provider without Python-side setup.

    The real LCA LLMAdapter (e.g. ``OpenAICompatAdapter``) reads
    ``LLM_API_KEY`` / ``LLM_MODEL`` / ``LLM_BASE_URL`` from the env at
    construction time; this wrapper passes nothing opaque and lets the
    adapter do its env resolution.
    """

    def __init__(
        self,
        adapter: Any | None = None,
        *,
        adapter_factory: dict | None = None,
    ) -> None:
        if adapter is None and adapter_factory is None:
            raise ValueError("LcaLlmProvider needs either `adapter` or `adapter_factory`")
        if adapter is not None:
            self._adapter = adapter
            return
        ref = adapter_factory["ref"]
        kwargs = dict(adapter_factory.get("kwargs", {}) or {})
        module_name, _, class_name = ref.partition(":")
        if not module_name or not class_name:
            raise ValueError(f"adapter_factory.ref must be 'module:Class', got {ref!r}")
        module = importlib.import_module(module_name)
        cls = getattr(module, class_name)
        self._adapter = cls(**kwargs)

    def complete(
        self,
        *,
        messages_artifact: Artifact | None,
    ) -> Artifact:
        messages = messages_artifact.content if messages_artifact is not None else []
        if not isinstance(messages, list):
            messages = [{"role": "user", "content": str(messages)}]
        prompt = self._flatten(messages)
        # The wrapped adapter is async; this provider is sync (call_llm
        # node.execute() is sync). Bridge with asyncio.run — safe inside
        # a sync context, one round-trip per call.
        response = asyncio.run(self._adapter.complete(prompt))
        text = getattr(response, "text", "") or ""
        return make_message(text, content=text)

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


__all__ = ["LcaLlmProvider", "make_message_artifact"]
