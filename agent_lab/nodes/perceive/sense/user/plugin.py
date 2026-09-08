"""perceive.sense.user — pass through the current user message + state.

Pure read-only fold. The node DOES NOT write into state. State is an
inert snapshot passed through to the next node; the only output this
node emits is the user_message artifact (already an Artifact).

Per ADR-0194 C4 (Reducer 单写) and ADR-0191 DSH (Derive-from-Session-
History): facts live in Session log, state is a read-only projection.
sense.user's job is "carry this turn's user message forward", not
"mutate state.user_input".

The user message is the FULL OpenAI-style message (preserving
attachments verbatim); downstream perceive_aggregate reads it from the
artifact stream.

State is forwarded untouched. History is NOT owned here — history_derive
(remember__fold_history) folds Session log into _initial.history, which
model_eye consumes directly.
"""
from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node


@node(
    id="perceive.sense.user",
    layer=NodeLayer.MODEL_VISIBLE,
    kind=NodeKind.TRANSFORMER,
    description="Pass-through: forward state (read-only) and the current user message artifact. No state mutation.",
    inputs=[
        PortInfo("user_turn_in", kind=PortKind.MESSAGE),
    ],
    outputs=[
        PortInfo("user_turn_out", kind=PortKind.MESSAGE),
    ],
)
class SenseUser(Node):
    name = "perceive.sense.user"

    def execute(self, node, inputs):
        # Pass-through: re-emit user_turn on its OUT port.
        # Per first-principles perceive: each sense is a pure read-only
        # fold that carries its sensor artifact forward. No state, no hub.
        return {
            "user_turn_out": inputs.get("user_turn_in"),
        }
