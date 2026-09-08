"""reflect.join — assemble observation + decision (+ prior) into one combined fact.

Pure assemble. No critique, no memory, no side effects.
"""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="reflect.join",
    layer=NodeLayer.PHASE,
    kind=NodeKind.ASSEMBLER,
    description=(
        "Merge in_observation + in_decision (+ optional in_prior_reflection) "
        "into one combined FACT for critique."
    ),
    inputs=[
        PortInfo("in_observation", kind=PortKind.FACT, required=False),
        PortInfo("in_decision", kind=PortKind.FACT, required=False),
        PortInfo("in_prior_reflection", kind=PortKind.FACT, required=False),
    ],
    outputs=[PortInfo("combined", kind=PortKind.FACT)],
    provides=["reflect_combined"],
    emits=["combined"],
    relates_to=["reflect.critique"],
)
class ReflectJoin(Node):
    name = "reflect.join"

    def execute(self, node, inputs):
        out = node.config.get("to", "combined") if getattr(node, "config", None) else "combined"
        if getattr(node, "outs", None):
            out = node.outs[0]
        merged: dict = {}
        for port_name, artifact in inputs.items():
            content = artifact.content if artifact is not None else None
            merged[port_name] = content if isinstance(content, dict) else {"_raw": content}
        return {
            out: Artifact(
                kind=ArtifactKind.FACT,
                content=merged,
                schema_ref="reflect.combined.v1",
            )
        }
