"""tail_event_node — Session.snapshot_events(from_seq, limit) → events list.

Single-purpose adapter node. Wraps LcaEventTailProvider to read recent
events from the LCA Session. Returns an events artifact (list of dicts).

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
    id="tail_event_node",
    name="tail_event_node",
    layer=NodeLayer.LINEAGE,
    kind=NodeKind.EXECUTOR,
    description=(
        "Read recent events via Session.snapshot_events(from_seq, limit). "
        "Returns an events artifact (list of dicts)."
    ),
    inputs=[
        PortInfo("in_from_seq", kind=PortKind.FACT, required=False),
        PortInfo("in_limit", kind=PortKind.FACT, required=False),
    ],
    outputs=[PortInfo("events", kind=PortKind.FACT)],
    provides=["event_tail"],
    requires=["session_snapshot"],
    emits=["events"],
    relates_to=["emit_event_node"],
)
class TailEventNode(Node):
    """Bridge agent_lab tail → Session.snapshot_events via LcaEventTailProvider."""

    name = "tail_event_node"

    def execute(self, node, inputs):
        from agent_lab.adapters.lca_event import LcaEventTailProvider

        provider = LcaEventTailProvider.from_node_config(node.config)
        return provider.tail(
            in_from_seq_artifact=inputs.get("in_from_seq"),
            in_limit_artifact=inputs.get("in_limit"),
        )
