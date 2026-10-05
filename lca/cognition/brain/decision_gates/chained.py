"""Chain multiple DecisionGate implementations in order.

Gate verdicts are durable Session facts (``gate.decided.v1``). The
``record_gate_decided`` helper is the single production choke point.
"""

from __future__ import annotations

from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.models.core.policy.gate_policy import GateDecided
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols import DecisionGate
from lca.infrastructure.session.emit.cognitive_emit import emit_gate_decided_from_policy


class ChainedDecisionGate(DecisionGate):
    """Apply gates sequentially; each gate may rewrite the decision.

    Observability (todo-28 C2): per-gate ``evaluated`` / ``intercepted``
    counters. A gate counts as *intercepted* when the Decision it returns
    differs (``!=``) from the one it received, i.e. it rewrote the candidate
    instead of passing it through. Counters are keyed by gate class name
    (the DecisionGate protocol exposes no stable id) and are cumulative over
    this chain instance's lifetime; call :meth:`reset_gate_counters` to start
    a fresh observation window. Per-step durable verdicts remain the
    ``gate.decided.v1`` Session facts recorded by the gates themselves.
    """

    def __init__(self, *gates: DecisionGate) -> None:
        self._gates = gates
        self._counters: dict[str, dict[str, int]] = {
            type(gate).__name__: {"evaluated": 0, "intercepted": 0}
            for gate in gates
        }

    async def enforce(self, state: AgentState, decision: Decision) -> Decision:
        current = decision
        for gate in self._gates:
            name = type(gate).__name__
            self._counters[name]["evaluated"] += 1
            rewritten = await gate.enforce(state, current)
            if rewritten != current:
                self._counters[name]["intercepted"] += 1
            current = rewritten
        return current

    def gate_counters(self) -> dict[str, dict[str, int]]:
        """Snapshot of per-gate evaluated/intercepted counters (deep copy)."""
        return {name: dict(counts) for name, counts in self._counters.items()}

    def reset_gate_counters(self) -> None:
        """Zero all counters; starts a fresh observation window."""
        for counts in self._counters.values():
            counts["evaluated"] = 0
            counts["intercepted"] = 0


def record_gate_decided(state: AgentState, event: GateDecided) -> None:
    """Append a ``gate.decided.v1`` Session fact for the current think step."""
    emit_gate_decided_from_policy(state, event)


__all__ = ["ChainedDecisionGate", "record_gate_decided"]
