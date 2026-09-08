"""assemble_messages node — merge list[message] + system prompt into one ordered list."""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


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
        return {
            out_port: Artifact(
                kind=ArtifactKind.MESSAGE, content=messages, schema_ref="openai.messages.v1"
            )
        }
