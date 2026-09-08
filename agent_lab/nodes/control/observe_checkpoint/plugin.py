"""observe_checkpoint_node — emit a checkpoint event to event_log.

Single-node handler for the observe_checkpoint control slot
(ControlSlot.OBSERVE_CHECKPOINT). Cross-cutting observer; owner is None
in LCA terms, mapped to phase:agent_loop in the graph region.
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
    id="observe_checkpoint_node",
    name="observe_checkpoint_node",
    layer=NodeLayer.CONTROL,
    kind=NodeKind.PRODUCER,
    description=(
        "Control-slot handler for observe.checkpoint: emits a checkpoint "
        "event fact. Cross-cutting observer, no phase owner."
    ),
    inputs=[PortInfo("in_event_log", kind=PortKind.ARTIFACT, required=False)],
    outputs=[PortInfo("checkpoint_event", kind=PortKind.FACT)],
    provides=["control_observe_checkpoint"],
    requires=[],
    emits=["checkpoint"],
)
class ObserveCheckpointNode(Node):
    """Emit a checkpoint event via LcaControlCheckpointProvider."""

    name = "observe_checkpoint_node"

    def execute(self, node, inputs):
        from agent_lab.adapters.lca_control import LcaControlCheckpointProvider

        provider = LcaControlCheckpointProvider.from_node_config(node.config)
        out_port = node.config.get("to", "checkpoint_event")
        event_type = node.config.get("event_type", "checkpoint")
        return provider.emit(
            event_type=event_type,
            event_log=inputs.get("in_event_log"),
            out_port=out_port,
        )
