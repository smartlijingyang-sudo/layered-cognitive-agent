"""think.guard — DecisionGate.enforce inside the think phase.

Logic lives in ``ops.py`` (node purity: plugin.py has no data branching).
Gate ⊂ Think; control-slot think_guard is passthrough.
"""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.nodes.think.guard.ops import (
    enforce_decision,
    register_fixture_gate,
    unregister_fixture_gate,
)
from agent_lab.primitives.artifact import Artifact, ArtifactKind

__all__ = ["ThinkGuard", "register_fixture_gate", "unregister_fixture_gate"]

_GATE_KEYS = (
    "null_gate",
    "gate_factory",
    "fixture_gate_name",
    "allow_empty_chain",
    "gate",
)


@node(
    id="think.guard",
    layer=NodeLayer.PHASE,
    kind=NodeKind.EXECUTOR,
    description=(
        "Run DecisionGate.enforce(state, decision); emit enforced Decision and think_signal. "
        "Requires null_gate or an explicit gate; empty chains fail-loud."
    ),
    inputs=[
        PortInfo("decision", kind=PortKind.FACT, required=False),
        PortInfo("in_state", kind=PortKind.FACT, required=False),
        PortInfo("in_perception_signal", kind=PortKind.ARTIFACT, required=False),
    ],
    outputs=[
        PortInfo("enforced_decision", kind=PortKind.FACT),
        PortInfo("think_signal", kind=PortKind.FACT),
    ],
    provides=["decision_gate_enforced", "think_signal"],
    requires=["decision_gate"],
    emits=["enforced_decision", "think_signal"],
    relates_to=["think.classify"],
)
class ThinkGuard(Node):
    name = "think.guard"

    def execute(self, node, inputs):
        cfg = dict(node.config or {})
        provider_cfg = dict(cfg.get("provider_config") or {})
        # Top-level gate keys override provider_config (dict union order).
        merged = {
            **provider_cfg,
            **{k: cfg[k] for k in _GATE_KEYS if k in cfg},
        }
        src = cfg.get("from", "decision")
        out = cfg.get("to", "enforced_decision")
        result = enforce_decision(
            inputs.get(src) or inputs.get("decision"),
            inputs.get("in_state"),
            config=merged,
            out_port=out,
        )
        ports = node.outs or [out, "think_signal"]
        return {
            port: result.get(port, Artifact(kind=ArtifactKind.FACT, content=None)) for port in ports
        }
