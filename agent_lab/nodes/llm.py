"""LLM nodes — thin adapters that call a configured provider.

In this prototype, providers are in-process callables registered into
`llm_providers`.  Real wiring would replace this with an HTTP client.
"""

from __future__ import annotations

from agent_lab.graph.spec import InfoNode
from agent_lab.nodes.base import Node, register
from agent_lab.primitives.artifact import Artifact, ArtifactKind, make_message

_LLM_PROVIDERS: dict[str, callable] = {}  # name -> callable(messages) -> str


def register_llm_provider(name: str, fn) -> None:
    _LLM_PROVIDERS[name] = fn


@register
class CallLLM(Node):
    """Send messages, return assistant message."""

    name = "call_llm"

    def execute(self, node: InfoNode, inputs: dict[str, Artifact]) -> dict[str, Artifact]:
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


@register
class AssembleMessages(Node):
    """Merge list[message] + system prompt into one ordered list."""

    name = "assemble_messages"

    def execute(self, node: InfoNode, inputs: dict[str, Artifact]) -> dict[str, Artifact]:
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


@register
class CommitManifest(Node):
    """Wrap final messages into a frozen ContextManifest."""

    name = "commit_manifest"

    def execute(self, node: InfoNode, inputs: dict[str, Artifact]) -> dict[str, Artifact]:
        src = node.config.get("from", "messages")
        out_port = node.config.get("to", "manifest")
        src_a = inputs.get(src)
        messages = src_a.content if src_a else []
        return {out_port: Artifact(
            kind=ArtifactKind.MANIFEST,
            content={"messages": messages, "committed": True},
            schema_ref="context.manifest.v1",
        )}
