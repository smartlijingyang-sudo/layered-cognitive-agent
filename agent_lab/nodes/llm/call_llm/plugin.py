"""call_llm node — config-driven provider; no global registry.

Each call_llm node reads its provider from ``node.config``:
  - ``provider_ref``: dotted ``module:Class`` path to a provider class that
    accepts ``complete(messages_artifact) -> Artifact``. The real LCA
    adapter ``LcaLlmProvider`` wraps any ``lca.contracts.protocols.LLMAdapter``
    (e.g. ``OpenAICompatAdapter``); YAML declares it via
    ``adapter_factory: {ref, kwargs}``.
  - ``provider_config``: opaque dict passed to the provider's constructor.
  - ``provider_kind``: optional shorthand — ``"lca"`` maps to the default
    ``LcaLlmProvider`` so YAML stays terse.

No global registration. No Python-side setup. The graph config IS the
provider selection.
"""

from __future__ import annotations

import importlib

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind

_DEFAULT_PROVIDER_KINDS: dict[str, str] = {
    "lca": "agent_lab.adapters.lca_llm:LcaLlmProvider",
}


def _resolve_provider(node):
    """Read provider factory from node.config and instantiate it.

    Resolution order:
      1. ``provider_ref`` (module:Class) -> import + instantiate(**provider_config)
      2. ``provider_kind`` ('lca') -> map to default ``provider_ref``
      3. raise ConfigurationError
    """
    cfg = node.config or {}
    provider_ref = cfg.get("provider_ref")
    provider_kind = cfg.get("provider_kind")
    if provider_ref is None and provider_kind is not None:
        provider_ref = _DEFAULT_PROVIDER_KINDS.get(provider_kind)
    if provider_ref is None:
        raise RuntimeError(
            f"call_llm node '{node.id}' missing 'provider_ref' or 'provider_kind' in config"
        )
    module_name, _, class_name = provider_ref.partition(":")
    if not module_name or not class_name:
        raise RuntimeError(
            f"call_llm node '{node.id}': provider_ref must be 'module:Class', got {provider_ref!r}"
        )
    module = importlib.import_module(module_name)
    provider_cls = getattr(module, class_name)
    provider_config = cfg.get("provider_config", {}) or {}
    return provider_cls(**provider_config)


@node(
    id="call_llm",
    layer=NodeLayer.PHASE,
    kind=NodeKind.EXECUTOR,
    description=(
        "Send messages to a provider loaded from node.config (provider_ref or "
        "provider_kind). Returns an assistant message artifact. Provider is "
        "instantiated per-node on each execute(); no global registry."
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
    """Send messages to the configured provider; return assistant message."""

    name = "call_llm"

    def execute(self, node, inputs):
        messages_in = node.config.get("from", "messages")
        out_port = node.config.get("to", "response")
        msgs_a = inputs.get(messages_in)
        msgs = msgs_a.content if msgs_a else []
        if not isinstance(msgs, list):
            msgs = [{"role": "user", "content": str(msgs_a.content if msgs_a else "")}]
        messages_artifact = Artifact(
            kind=ArtifactKind.MESSAGE, content=msgs, schema_ref="openai.messages.v1"
        )
        provider = _resolve_provider(node)
        if not hasattr(provider, "complete"):
            raise RuntimeError(
                f"call_llm node '{node.id}': provider {type(provider).__name__} "
                "has no .complete() method"
            )
        return {out_port: provider.complete(messages_artifact=messages_artifact)}
