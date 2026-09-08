"""perceive.sense — Sensor.read(state) fold (Hub sense step)."""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node


@node(
    id="perceive.sense",
    layer=NodeLayer.PHASE,
    kind=NodeKind.TRANSFORMER,
    description="Fold Sensor.read(state) over resolved sensors into sensor_items.",
    inputs=[
        PortInfo("sensors", kind=PortKind.FACT, required=False),
        PortInfo("state", kind=PortKind.FACT, required=False),
    ],
    outputs=[PortInfo("sensor_items", kind=PortKind.FACT)],
    provides=["sensor_items"],
    requires=["sensors"],
    emits=["sensor_items"],
    relates_to=["perceive.resolve", "perceive.trim"],
)
class PerceiveSense(Node):
    name = "perceive.sense"

    def execute(self, node, inputs):
        from agent_lab.adapters.lca_perceive import fold_sensor_items

        del node
        return fold_sensor_items(
            sensors_artifact=inputs.get("sensors"),
            state_artifact=inputs.get("state"),
        )
