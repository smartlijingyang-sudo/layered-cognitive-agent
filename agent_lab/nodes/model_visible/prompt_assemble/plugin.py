"""prompt_assemble node — flatten an OpenAI-style message list into a prompt string.

This is the SINGLE point in agent_lab that knows how to turn a message
list into a prompt string. call_llm doesn't do this anymore.

Configuration (node.config):
  - role_prefix : str, default "["  — prefix for each role marker
  - role_suffix : str, default "]"  — suffix for each role marker
  - sep         : str, default "\n" — separator between role lines
  - from / to   : port renames (default: messages -> prompt)

Input: a MESSAGE artifact containing a list[dict] with role/content keys.
Output: a TEXT artifact carrying the flattened prompt string.

Lifecycle:
  Lives in the think / model-visible sub-graph (sibling of
  commit_manifest). Wired between assemble_messages / merge_messages
  and call_llm.
"""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="prompt_assemble",
    layer=NodeLayer.MODEL_VISIBLE,
    kind=NodeKind.TRANSFORMER,
    description=(
        "Flatten an OpenAI-style message list into a single prompt string. "
        "Owns the [role] prefix format used by the LLM adapter."
    ),
    inputs=[PortInfo("messages", kind=PortKind.MESSAGE, required=False)],
    outputs=[PortInfo("prompt", kind=PortKind.TEXT)],
    provides=["prompt_string"],
    requires=["message_list"],
    relates_to=["call_llm", "merge_messages", "assemble_messages"],
)
class PromptAssemble(Node):
    """messages list  ->  prompt string."""

    name = "prompt_assemble"

    def execute(self, node, inputs):
        in_port = node.config.get("from", "messages")
        out_port = node.config.get("to", "prompt")
        msg_a = inputs.get(in_port)
        messages = msg_a.content if msg_a else []
        if not isinstance(messages, list):
            messages = [{"role": "user", "content": str(msg_a.content if msg_a else "")}]

        prefix = node.config.get("role_prefix", "[")
        suffix = node.config.get("role_suffix", "]")
        sep = node.config.get("sep", "\n")

        parts: list[str] = []
        for m in messages:
            if not isinstance(m, dict):
                continue
            role = m.get("role", "user")
            content = m.get("content", "")
            parts.append(f"{prefix}{role}{suffix} {content}")
        return {out_port: Artifact(
            kind=ArtifactKind.TEXT,
            content=sep.join(parts),
            schema_ref="prompt.text.v1",
        )}
