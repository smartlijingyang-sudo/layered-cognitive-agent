"""LLM nodes — thin adapters that call a configured provider.

In this prototype, providers are in-process callables registered into
`llm_providers`.  Real wiring would replace this with an HTTP client.
"""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind, make_message

_LLM_PROVIDERS: dict[str, callable] = {}  # name -> callable(messages) -> str


def register_llm_provider(name: str, fn) -> None:
    _LLM_PROVIDERS[name] = fn


@node(
    id="call_llm",
    layer=NodeLayer.PHASE,
    kind=NodeKind.EXECUTOR,
    description="Send messages to a configured LLM provider; return assistant message.",
    inputs=[PortInfo("from", kind=PortKind.MESSAGE, required=False)],
    outputs=[PortInfo("to", kind=PortKind.MESSAGE)],
    provides=["llm_response"],
    requires=["message_list"],
    consumes=[],
    emits=["llm_call"],
    relates_to=["assemble_messages", "merge_messages"],
)
class CallLLM(Node):
    """Send messages, return assistant message."""

    name = "call_llm"

    def execute(self, node, inputs):
        provider = node.config["provider"]
        messages_in = node.config.get("from", "messages")
        out_port = node.config.get("to", "response")
        msgs_a = inputs.get(messages_in)
        msgs = msgs_a.content if msgs_a else []
        if not isinstance(msgs, list):
            msgs = [{"role": "user", "content": str(msgs_a.content if msgs_a else "")}]
        provider_fn = _LLM_PROVIDERS.get(provider)
        if provider_fn is None:
            raise RuntimeError(f"unknown LLM provider: {provider}")
        text = provider_fn(msgs)
        return {out_port: make_message("assistant", text)}


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
