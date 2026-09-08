"""perceive.sense.tool_results — pass through prior-turn tool results + state.

Pure read-only fold. The node DOES NOT write into state. State is an
inert snapshot passed through to the next node; the only output this
node emits is the tool_results artifact (already an Artifact).

Per ADR-0194 C4 (Reducer 单写) and ADR-0191 DSH: facts live in Session
log, state is a read-only projection. sense.tool_results's job is
"carry prior-turn tool result messages forward", not "mutate
state.tool_results".

Each tool result message is OpenAI-style {role: "tool", tool_call_id,
content}; attachments inside content are preserved verbatim. Downstream
perceive_aggregate reads them from the artifact stream.

History is NOT owned here — history_derive (remember__fold_history)
folds Session log into _initial.history, which model_eye consumes
directly.
"""
from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node


@node(
    id="perceive.sense.tool_results",
    layer=NodeLayer.MODEL_VISIBLE,
    kind=NodeKind.TRANSFORMER,
    description="Pass-through: forward state (read-only) and the prior-turn tool results artifact. No state mutation.",
    inputs=[
        PortInfo("tool_results_in", kind=PortKind.MESSAGE),
    ],
    outputs=[
        PortInfo("tool_results_out", kind=PortKind.MESSAGE),
    ],
)
class SenseToolResults(Node):
    name = "perceive.sense.tool_results"

    def execute(self, node, inputs):
        # Pass-through: re-emit tool_results on its OUT port.
        # Per first-principles perceive: each sense is a pure read-only
        # fold that carries its sensor artifact forward. No state, no hub.
        return {
            "tool_results_out": inputs.get("tool_results_in"),
        }
