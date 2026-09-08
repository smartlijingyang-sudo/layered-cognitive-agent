"""remember_admit_node — decide whether an observation is admitted to memory.

Single-node handler for the remember_admit control slot
(ControlSlot.REMEMBER_ADMIT). Owner: memory phase. Acts as a filter:
returns an admit_verdict FACT with {"admitted": bool}.
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
    id="remember_admit_node",
    name="remember_admit_node",
    layer=NodeLayer.CONTROL,
    kind=NodeKind.VALIDATOR,
    description=(
        "Control-slot handler for remember.admit: decides whether an "
        "observation should be admitted to memory (filter)."
    ),
    inputs=[PortInfo("in_observation", kind=PortKind.FACT, required=False)],
    outputs=[PortInfo("admit_verdict", kind=PortKind.FACT)],
    provides=["control_remember_admit"],
    requires=["memory_admit_policy"],
    emits=["admit_verdict"],
)
class RememberAdmitNode(Node):
    """Decide memory admission via LcaControlRememberAdmitProvider."""

    name = "remember_admit_node"

    def execute(self, node, inputs):
        from agent_lab.adapters.lca_control import LcaControlRememberAdmitProvider

        provider = LcaControlRememberAdmitProvider.from_node_config(node.config)
        out_port = node.config.get("to", "admit_verdict")
        return provider.admit(
            observation=inputs.get("in_observation"),
            out_port=out_port,
        )
