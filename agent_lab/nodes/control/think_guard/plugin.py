"""think_guard_node — control-slot attachment for THINK_GUARD.

Phase ``think.guard`` is the SSOT for DecisionGate.enforce. This control
slot defaults to passthrough so the decision is not double-enforced.
"""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.control.think_guard.ops import handle_control_decision
from agent_lab.nodes.manifest import (
    NodeKind,
    NodeLayer,
    PortInfo,
    PortKind,
    node,
)


@node(
    id="think_guard_node",
    name="think_guard_node",
    layer=NodeLayer.CONTROL,
    kind=NodeKind.EXECUTOR,
    description=(
        "Control-slot handler for think.guard attachment. "
        "Default mode=passthrough (phase think.guard owns enforce)."
    ),
    inputs=[PortInfo("in_decision", kind=PortKind.FACT, required=False)],
    outputs=[PortInfo("out_decision", kind=PortKind.FACT)],
    provides=["control_think_guard"],
    requires=["decision_gate"],
    emits=["guarded_decision"],
)
class ThinkGuardNode(Node):
    name = "think_guard_node"

    def execute(self, node, inputs):
        cfg = node.config or {}
        provider_cfg = dict(cfg.get("provider_config") or {})
        mode = str(provider_cfg.get("mode") or cfg.get("mode") or "passthrough")
        out_port = cfg.get("to", "out_decision")
        enforce_cfg = {k: v for k, v in provider_cfg.items() if k != "mode"}
        return handle_control_decision(
            inputs.get("in_decision"),
            mode=mode,
            out_port=out_port,
            enforce_config=enforce_cfg,
        )
