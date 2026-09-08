"""stop_focus_node — focus-aware stop governance for the stop phase.

Single-node handler for the stop_focus control slot
(ControlSlot.STOP_DECIDE side-channel; LCA's
``lca.plugins.loop.control.stop_focus.FocusStopExecutor``).

Counts consecutive stagnant turns (unsuccessful observation +
reflection correction/blockage + identical intent) and emits a
``focus_verdict`` FACT with ``{kind: allow|stop, count: int,
limit: int, detail: str}``.

Default fallback (``_AlwaysFocus``) returns ``count: 0`` → always
``allow`` so dry runs / tests do not trip the focus policy unless a
fixture is injected.
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
    id="stop_focus_node",
    name="stop_focus_node",
    layer=NodeLayer.CONTROL,
    kind=NodeKind.VALIDATOR,
    description=(
        "Control-slot handler for stop.focus: counts consecutive stagnant "
        "turns and emits a focus_verdict (allow / stop)."
    ),
    inputs=[
        PortInfo("in_state", kind=PortKind.ARTIFACT, required=False),
        PortInfo("in_decision", kind=PortKind.FACT, required=False),
    ],
    outputs=[PortInfo("focus_verdict", kind=PortKind.FACT)],
    provides=["control_stop_focus"],
    requires=["state_history"],
    emits=["focus_verdict"],
)
class StopFocusNode(Node):
    """Bridge state + decision → focus_verdict via LcaControlStopFocusProvider."""

    name = "stop_focus_node"

    def execute(self, node, inputs):
        from agent_lab.adapters.lca_control import LcaControlStopFocusProvider

        provider = LcaControlStopFocusProvider.from_node_config(node.config)
        out_port = node.config.get("to", "focus_verdict")
        return provider.evaluate(
            state=inputs.get("in_state"),
            decision=inputs.get("in_decision"),
            out_port=out_port,
        )
