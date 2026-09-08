"""call_llm node — invoke LCA LLMAdapter directly.

Fusion refactor (2026-09-08): removed LcaLlmProvider adapter layer.
This node now imports any LLMAdapter Protocol implementation directly.

Configuration (node.config):
  - adapter_factory: {ref: "module:Class", kwargs: {}}
      Resolves to an LLMAdapter instance (e.g. OpenAICompatAdapter).
  - from / to: port renames (default: messages -> response)

The default `provider_kind: lca` maps to OpenAICompatAdapter (the real
LCA adapter) — same semantics as before, fewer indirections.

Node responsibility boundary:
  - call_llm DOES NOT handle message-list structure. It hands the
    artifact's content to the configured LLMAdapter.
  - The current LCA OpenAICompatAdapter.complete(prompt: str) accepts a
    string prompt, not a list-of-messages. To preserve that contract
    while staying close to the node's "just call the adapter" role,
    the node flattens the OpenAI-style message list into a single
    prompt string with [role] prefixes.
  - This is documented as a known limitation: when LCA ships an
    LLMAdapter that accepts message lists natively, the flatten step
    disappears. Until then, the node holds the flatten to keep the
    adapter call minimal.

Behaviour:
  - messages list is flattened to a single prompt string
  - adapter.complete(prompt) is awaited via asyncio.run (sync bridge)
  - response.text is wrapped in a make_message artifact
"""

from __future__ import annotations

import asyncio
import importlib

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind, make_message

_DEFAULT_PROVIDER_KINDS: dict[str, str] = {
    "lca": "lca.infrastructure.llm_adapter.openai_compat:OpenAICompatAdapter",
}


def _resolve_adapter(node):
    """Read LLMAdapter factory from node.config and instantiate it.

    Resolution order:
      1. ``adapter_factory`` ({ref, kwargs}) -> import + instantiate(**kwargs)
      2. ``provider_ref`` (module:Class) -> import + instantiate(**provider_config)
      3. ``provider_kind`` ('lca') -> map to default adapter_factory
    """
    cfg = node.config or {}
    factory = cfg.get("adapter_factory")
    if factory is None:
        provider_ref = cfg.get("provider_ref")
        provider_kind = cfg.get("provider_kind")
        if provider_ref is None and provider_kind is not None:
            provider_ref = _DEFAULT_PROVIDER_KINDS.get(provider_kind)
        if provider_ref is None:
            raise RuntimeError(
                f"call_llm node '{node.id}' missing adapter_factory / provider_ref / provider_kind"
            )
        factory = {"ref": provider_ref, "kwargs": dict(cfg.get("provider_config", {}) or {})}
    ref = factory["ref"]
    kwargs = dict(factory.get("kwargs", {}) or {})
    module_name, _, class_name = ref.partition(":")
    if not module_name or not class_name:
        raise ValueError(f"adapter_factory.ref must be 'module:Class', got {ref!r}")
    module = importlib.import_module(module_name)
    cls = getattr(module, class_name)
    return cls(**kwargs)


@node(
    id="call_llm",
    layer=NodeLayer.PHASE,
    kind=NodeKind.EXECUTOR,
    description=(
        "Send messages to an LLMAdapter resolved from node.config. Returns "
        "an assistant message artifact. Adapter is instantiated per-node; "
        "no global registry."
    ),
    inputs=[PortInfo("from", kind=PortKind.MESSAGE, required=False)],
    outputs=[PortInfo("to", kind=PortKind.MESSAGE)],
    provides=["llm_response"],
    requires=["message_list"],
    consumes=[],
    emits=["llm_call"],
    relates_to=["assemble_messages", "merge_messages"],
)
class CallLLM(Node):
    """Send messages to a real LLMAdapter; return assistant message."""

    name = "call_llm"

    def execute(self, node, inputs):
        messages_in = node.config.get("from", "messages")
        out_port = node.config.get("to", "response")
        msgs_a = inputs.get(messages_in)
        msgs = msgs_a.content if msgs_a else []
        if not isinstance(msgs, list):
            msgs = [{"role": "user", "content": str(msgs_a.content if msgs_a else "")}]

        adapter = _resolve_adapter(node)
        prompt = self._flatten(msgs)
        # LLMAdapter.complete is async; bridge to sync with asyncio.run.
        response = asyncio.run(adapter.complete(prompt))
        text = getattr(response, "text", "") or ""
        return {out_port: make_message(text, content=text)}

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
