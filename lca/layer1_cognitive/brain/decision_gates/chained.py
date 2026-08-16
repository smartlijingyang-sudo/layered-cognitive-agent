"""Chain multiple DecisionGate implementations in order."""

from __future__ import annotations

from lca.contracts.models.core.decision import Decision
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols import DecisionGate


class ChainedDecisionGate(DecisionGate):
    """Apply gates sequentially; each gate may rewrite the decision."""

    def __init__(self, *gates: DecisionGate) -> None:
        self._gates = gates

    async def enforce(self, state: AgentState, decision: Decision) -> Decision:
        current = decision
        for gate in self._gates:
            current = await gate.enforce(state, current)
        return current
