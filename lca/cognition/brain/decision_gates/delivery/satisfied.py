"""DeliverySatisfiedGate — block producer tools after delivery (ADR-0196)."""

from __future__ import annotations

from lca.cognition.brain.decision_gates.chained.chained import record_gate_decided
from lca.cognition.convergence.runtime import ConvergenceRuntime
from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.models.core.policy.gate_policy import GateDecided, PolicyFact
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols import DecisionGate
from lca.contracts.protocols.think.convergence import ConvergencePolicy

_RATIONALE = "交付证据已满足：禁止继续工具调用，必须 respond 收口。"


class DeliverySatisfiedGate(DecisionGate):
    """Rewrite USE_TOOL decisions to RESPOND when delivery is satisfied."""

    def __init__(self, runtime: ConvergenceRuntime | ConvergencePolicy | None = None) -> None:
        if isinstance(runtime, ConvergenceRuntime):
            self._runtime = runtime
        else:
            from lca.cognition.convergence.policy import DefaultConvergencePolicy

            policy = runtime or DefaultConvergencePolicy()
            self._runtime = ConvergenceRuntime(policy=policy)

    async def enforce(self, state: AgentState, decision: Decision) -> Decision:
        evidence, _verdict = self._runtime.evaluate_and_emit(state)

        if decision.action_type != ActionType.USE_TOOL or not decision.tool_calls:
            return decision
        if not evidence.satisfied:
            return decision
        tool_name = decision.tool_calls[0].tool_name

        response_text = self._runtime.synthesize(
            state,
            evidence,
            existing_text=decision.response_text or "",
        )
        forced = Decision(
            decision_id=decision.decision_id,
            action_type=ActionType.RESPOND,
            rationale=_RATIONALE,
            confidence=0.95,
            response_text=response_text,
            degraded_from=decision.action_type,
        )
        record_gate_decided(
            state,
            GateDecided(
                event_id=new_id("gate"),
                gate="DeliverySatisfiedGate",
                verdict="rewrite",
                is_rewritten=True,
                tool_name=tool_name,
                rationale=_RATIONALE,
                policy_fact=PolicyFact(
                    kind="delivery_satisfied",
                    message=evidence.detail,
                    source="delivery_satisfied",
                    extra=evidence.as_dict(),
                ),
            ),
        )
        return forced


__all__ = ["DeliverySatisfiedGate"]
