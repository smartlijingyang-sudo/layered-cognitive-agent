"""Chain multiple DecisionGate implementations in order.

PR4: the chain has a single helper ``record_gate_decided`` that all
gates MUST call when they rewrite, deny, or warn.  Allow verdicts are
NOT recorded (per spec §3.5 — allow 默认不记, 避免日志噪声).

The helper is the typed entry point over ``PerceiveState``.  It writes
into ``state.extra[\"gate_decided\"]`` (the only sanctioned magic key
for the v3 Perceive fold) but the magic key lives in the typed
``perceive_state`` module — call sites never repeat the string.
"""

from __future__ import annotations

from lca.contracts.models.core.decision import Decision
from lca.contracts.models.core.gate_policy import GateDecided
from lca.contracts.models.core.perceive_state import record_event_to_state
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


def record_gate_decided(state: AgentState, event: GateDecided) -> None:
    """Append a ``GateDecided`` event to the running trace on state.

    The contract: every gate that *rewrites* or *denies* MUST call this
    helper.  ``warn`` verdicts SHOULD call it.  ``allow`` verdicts MUST
    NOT (allow 默认不记).

    The events are consumed by the next ``ContextManifest`` fold (per
    PR3a) so the PolicyFact reaches the LLM through the Manifest, not
    via direct ``state.working_memory`` access.
    """
    record_event_to_state(state, event)
