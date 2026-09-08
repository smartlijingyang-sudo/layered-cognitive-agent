"""observe_wildcard_node — wildcard observer for the observe.* control slot.

Single-node handler for the observe_wildcard control slot
(ControlSlot.OBSERVE_WILDCARD). Cross-cutting observer with no phase
owner; mirrors LCA's ``ObserveWildcardExecutor.execute`` semantics
(always returns verdict=allow).

Reads ``in_event`` (the cross-cutting event payload); emits a
``wildcard_event`` FACT with ``{verdict: allow, event_type, ts}``.
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
    id="observe_wildcard_node",
    name="observe_wildcard_node",
    layer=NodeLayer.CONTROL,
    kind=NodeKind.PRODUCER,
    description=(
        "Control-slot handler for observe.wildcard: wraps the wildcard "
        "observer (always returns verdict=allow in the no-op owner)."
    ),
    inputs=[PortInfo("in_event", kind=PortKind.ARTIFACT, required=False)],
    outputs=[PortInfo("wildcard_event", kind=PortKind.FACT)],
    provides=["control_observe_wildcard"],
    requires=[],
    emits=["wildcard"],
)
class ObserveWildcardNode(Node):
    """Bridge cross-cutting event → wildcard verdict via LcaControlObserveWildcardProvider."""

    name = "observe_wildcard_node"

    def execute(self, node, inputs):
        from agent_lab.adapters.lca_control_act import LcaControlObserveWildcardProvider

        provider = LcaControlObserveWildcardProvider.from_node_config(node.config)
        out_port = node.config.get("to", "wildcard_event")
        event_type = node.config.get("event_type", "wildcard")
        return provider.emit(
            event_type=event_type,
            in_event=inputs.get("in_event"),
            out_port=out_port,
        )
