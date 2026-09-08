"""emit_event_node — Session.append(event_type, data) → event_fact.

Single-purpose adapter node. Wraps LcaEventEmitProvider to write one
durable fact through the LCA Session. Returns an event_fact artifact
carrying the SessionEvent's seq and id.

No branching on data values. Config is JSON-serializable.
See agent_lab/graphs/configs/event_log.yaml for the canonical call site.
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


@node(
    id="emit_event_node",
    name="emit_event_node",
    layer=NodeLayer.LINEAGE,
    kind=NodeKind.EXECUTOR,
    description=(
        "Write one durable fact via Session.append(event_type, data). "
        "Returns an event_fact artifact with seq and id."
    ),
    inputs=[
        PortInfo("event_type", kind=PortKind.TEXT, required=True),
        PortInfo("event_data", kind=PortKind.FACT, required=False),
    ],
    outputs=[PortInfo("event_fact", kind=PortKind.FACT)],
    provides=["event_emit"],
    requires=["session_append"],
    emits=["event_fact"],
    relates_to=["tail_event_node"],
)
class EmitEventNode(Node):
    """Bridge agent_lab emit → Session.append via LcaEventEmitProvider."""

    name = "emit_event_node"

    def execute(self, node, inputs):
        from agent_lab.adapters.lca_event import LcaEventEmitProvider

        provider = LcaEventEmitProvider.from_node_config(node.config)
        return provider.emit(
            event_type_artifact=inputs.get("event_type"),
            event_data_artifact=inputs.get("event_data"),
        )
