"""gather_inputs — join in_observation + in_decision into a combined artifact.

Pure combiner: bundles the observation and decision dicts into a single
FACT artifact so downstream critic / memory nodes can consume one input
instead of two.  No branching on data values.
"""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import (
    NodeKind,
    NodeLayer,
    PortInfo,
    PortKind,
    node,
)
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="gather_inputs",
    name="gather_inputs",
    layer=NodeLayer.PHASE,
    kind=NodeKind.TRANSFORMER,
    description=(
        "Merge in_observation + in_decision (+ optional in_prior_reflection) "
        "into a single combined FACT artifact for the reflect chain."
    ),
    inputs=[
        PortInfo("in_observation", kind=PortKind.FACT, required=False),
        PortInfo("in_decision", kind=PortKind.FACT, required=False),
        PortInfo("in_prior_reflection", kind=PortKind.FACT, required=False),
    ],
    outputs=[PortInfo("combined", kind=PortKind.FACT)],
    provides=["reflect_combined"],
    emits=["combined"],
    relates_to=["call_critic"],
)
class GatherInputsNode(Node):
    """Bundle observation + decision into one combined artifact."""

    name = "gather_inputs"

    def execute(self, node, inputs):
        out_port = node.outs[0] if node.outs else "combined"
        merged: dict = {}
        for port_name, artifact in inputs.items():
            content = artifact.content if artifact is not None else None
            merged[port_name] = content if isinstance(content, dict) else {"_raw": content}
        return {
            out_port: Artifact(
                kind=ArtifactKind.FACT,
                content=merged,
                schema_ref="reflect.combined.v1",
            )
        }
