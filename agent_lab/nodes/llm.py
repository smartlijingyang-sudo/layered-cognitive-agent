"""LLM nodes — thin adapters driven by graph config (no global registry).

Each call_llm node reads its provider from ``node.config``:
  - ``provider_ref``: dotted ``module:Class`` path to a provider class that
    accepts ``complete(messages_artifact) -> Artifact`` (see
    ``agent_lab.adapters.lca_llm.LcaLlmProvider`` for the LCA shape).
  - ``provider_config``: opaque dict passed to the provider's constructor.
  - ``provider_kind``: optional shorthand — ``"lca"`` / ``"mock"`` map to
    default provider_ref paths so YAML stays terse.

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
      2. ``provider_kind`` ('lca' | 'mock') -> map to default ``provider_ref``
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
        # Wrap msgs into a Message artifact the provider can consume.
        messages_artifact = Artifact(
            kind=ArtifactKind.MESSAGE, content=msgs, schema_ref="openai.messages.v1"
        )
        provider = _resolve_provider(node)
        # Providers expose complete(messages_artifact) -> Artifact.
        if not hasattr(provider, "complete"):
            raise RuntimeError(
                f"call_llm node '{node.id}': provider {type(provider).__name__} "
                "has no .complete() method"
            )
        return {out_port: provider.complete(messages_artifact=messages_artifact)}


@node(
    id="assemble_messages",
    layer=NodeLayer.PHASE,
    kind=NodeKind.ASSEMBLER,
    description="Merge list[message] + system prompt into one ordered list.",
    inputs=[
        PortInfo("system", kind=PortKind.TEXT, required=False),
        PortInfo("user", kind=PortKind.TEXT, required=False),
        PortInfo("history", kind=PortKind.MESSAGE, required=False),
    ],
    outputs=[PortInfo("to", kind=PortKind.MESSAGE)],
    provides=["message_list"],
    requires=["system_prompt"],
    relates_to=["call_llm", "merge_messages", "commit_manifest"],
)
class AssembleMessages(Node):
    """Merge list[message] + system prompt into one ordered list."""

    name = "assemble_messages"

    def execute(self, node, inputs):
        system_a = inputs.get("system")
        user_a = inputs.get("user")
        history_a = inputs.get("history")
        out_port = node.config.get("to", "messages")
        messages: list[dict] = []
        if system_a is not None:
            messages.append({"role": "system", "content": str(system_a.content)})
        if history_a is not None and isinstance(history_a.content, list):
            messages.extend(history_a.content)
        if user_a is not None:
            messages.append({"role": "user", "content": str(user_a.content)})
        return {out_port: Artifact(kind=ArtifactKind.MESSAGE, content=messages, schema_ref="openai.messages.v1")}


@node(
    id="commit_manifest",
    layer=NodeLayer.MODEL_VISIBLE,
    kind=NodeKind.PRODUCER,
    description="Wrap final messages into a frozen ContextManifest.",
    inputs=[PortInfo("from", kind=PortKind.MESSAGE, required=False)],
    outputs=[PortInfo("to", kind=PortKind.MANIFEST)],
    provides=["context_manifest"],
    requires=["message_list"],
    relates_to=["assemble_messages", "validate_manifest"],
)
class CommitManifest(Node):
    """Wrap final messages into a frozen ContextManifest."""

    name = "commit_manifest"

    def execute(self, node, inputs):
        src = node.config.get("from", "messages")
        out_port = node.config.get("to", "manifest")
        src_a = inputs.get(src)
        messages = src_a.content if src_a else []
        return {out_port: Artifact(
            kind=ArtifactKind.MANIFEST,
            content={"messages": messages, "committed": True},
            schema_ref="context.manifest.v1",
        )}
