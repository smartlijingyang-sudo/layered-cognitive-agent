"""Chain multiple DecisionGate implementations in order.

Gate verdicts are durable Session facts (``gate.decided.v1``). The
``record_gate_decided`` helper is the single production choke point.
"""

from __future__ import annotations

from lca.contracts.models.core.decision import Decision
from lca.contracts.models.core.gate_policy import GateDecided
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols import DecisionGate
from lca.infrastructure.session.cognitive_emit import emit_gate_decided_from_policy


class ChainedDecisionGate(DecisionGate):
    """Apply gates sequentially; each gate may rewrite the decision."""

    def __init__(self, *gates: DecisionGate) -> None:
        self._gates = gates

    async def enforce(self, state: AgentState, decision: Decision) -> Decision:
        current = decision
        for gate in self._gates:
            current = await gate.enforce(state, current)
        return current


def record_gate_decided(state: AgentState, event: GateDecided) -> None:
    """Append a ``gate.decided.v1`` Session fact for the current think step."""
    emit_gate_decided_from_policy(state, event)
