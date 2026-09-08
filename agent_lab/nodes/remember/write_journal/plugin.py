"""write_journal — call Session.append via LcaRememberJournalProvider.

Reads in_reflection + in_observation + in_decision, builds a fact payload,
and writes it to the Session (the sole fact-write seam per ADR-0186/0191/0194).
Emits journal_fact with the SessionEvent's seq + id.

Provider selection is data, not code; see
    agent_lab/graphs/configs/remember.yaml for the canonical call site.
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
    id="write_journal",
    name="write_journal",
    layer=NodeLayer.PHASE,
    kind=NodeKind.EXECUTOR,
    description=(
        "Append a durable fact to the Session (ADR-0186/0191/0194) from "
        "the remember phase's three inputs: reflection, observation, decision."
    ),
    inputs=[
        PortInfo("in_reflection", kind=PortKind.FACT, required=False),
        PortInfo("in_observation", kind=PortKind.FACT, required=False),
        PortInfo("in_decision", kind=PortKind.FACT, required=False),
    ],
    outputs=[PortInfo("journal_fact", kind=PortKind.FACT)],
    provides=["journal_fact"],
    requires=["session_append"],
    emits=["journal_fact"],
    relates_to=["save_state"],
)
class WriteJournalNode(Node):
    """Bridge remember inputs → Session.append via LcaRememberJournalProvider."""

    name = "write_journal"

    def execute(self, node, inputs):
        from agent_lab.adapters.lca_memory import LcaRememberJournalProvider

        provider = LcaRememberJournalProvider.from_node_config(node.config)
        out_port = node.config.get("to", "journal_fact")
        return provider.append_journal(
            reflection_artifact=inputs.get("in_reflection"),
            observation_artifact=inputs.get("in_observation"),
            decision_artifact=inputs.get("in_decision"),
            out_port=out_port,
        )
