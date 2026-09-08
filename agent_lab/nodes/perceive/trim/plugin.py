"""perceive.trim — ContextBudgeter.trim over sensor/memory/policy items."""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node


@node(
    id="perceive.trim",
    layer=NodeLayer.PHASE,
    kind=NodeKind.TRANSFORMER,
    description="Concatenate Hub item streams and apply ContextBudgeter.trim.",
    inputs=[
        PortInfo("sensor_items", kind=PortKind.FACT, required=False),
        PortInfo("memory_items", kind=PortKind.FACT, required=False),
        PortInfo("policy_items", kind=PortKind.FACT, required=False),
    ],
    outputs=[PortInfo("trimmed_items", kind=PortKind.FACT)],
    provides=["trimmed_items"],
    requires=["context_budget"],
    emits=["trimmed_items"],
    relates_to=["perceive.sense", "perceive.memory", "perceive.policy", "perceive.commit"],
)
class PerceiveTrim(Node):
    name = "perceive.trim"

    def execute(self, node, inputs):
        from agent_lab.adapters.lca_perceive import trim_items

        cfg = getattr(node, "config", None) or {}
        max_chars = cfg.get("max_chars")
        return trim_items(
            sensor_items=inputs.get("sensor_items"),
            memory_items=inputs.get("memory_items"),
            policy_items=inputs.get("policy_items"),
            max_chars=int(max_chars) if max_chars is not None else None,
        )
