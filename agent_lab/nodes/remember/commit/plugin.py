"""remember.commit — Session.append for the turn's durable fact.

Sole fact-write seam for the remember phase (ADR-0186/0191/0194).
Consumes reflection / observation / decision / admitted; emits journal_fact.
"""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node


@node(
    id="remember.commit",
    layer=NodeLayer.PHASE,
    kind=NodeKind.EXECUTOR,
    description=(
        "Append remember.turn_fact via Session.append from reflection, "
        "observation, decision, and admitted candidates."
    ),
    inputs=[
        PortInfo("in_reflection", kind=PortKind.FACT, required=False),
        PortInfo("in_observation", kind=PortKind.FACT, required=False),
        PortInfo("in_decision", kind=PortKind.FACT, required=False),
        PortInfo("admitted", kind=PortKind.FACT, required=False),
    ],
    outputs=[PortInfo("journal_fact", kind=PortKind.FACT)],
    provides=["journal_fact"],
    requires=["session_append"],
    emits=["journal_fact"],
    relates_to=["remember.admit", "remember.snapshot"],
)
class RememberCommit(Node):
    name = "remember.commit"

    def execute(self, node, inputs):
        from agent_lab.adapters.lca_memory import LcaRememberJournalProvider

        provider = LcaRememberJournalProvider.from_node_config(getattr(node, "config", None) or {})
        out_port = (getattr(node, "config", None) or {}).get("to", "journal_fact")
        return provider.append_journal(
            reflection_artifact=inputs.get("in_reflection"),
            observation_artifact=inputs.get("in_observation"),
            decision_artifact=inputs.get("in_decision"),
            admitted_artifact=inputs.get("admitted"),
            out_port=out_port,
        )
