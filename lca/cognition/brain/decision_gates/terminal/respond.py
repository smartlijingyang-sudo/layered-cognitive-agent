"""Terminal respond gate — reserve last step for user-facing closure (ADR-0051 + PR6).

PR4: rewrite verdicts MUST record a GateDecided event.  When the gate
forces a respond, a GateDecided event with verdict=rewrite is recorded.

PR6: the gate reads workspace artifacts **exclusively** from
``AgentState.perceive`` manifest items.  Live ``get_run_workspace()`` reads
from the Reasoner / Gates are forbidden (v3 §5.1) — the workspace is a
Sensor-owned surface.
"""

from __future__ import annotations

from lca.cognition.brain.decision_gates.chained.chained import record_gate_decided
from lca.cognition.convergence.delivery_synth import synthesize_delivery_response
from lca.cognition.convergence.evidence import build_delivery_evidence
from lca.cognition.convergence.producer_tools import is_producer_tool
from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.models.core.policy.budget import TERMINAL_RESERVE_STEPS
from lca.contracts.models.core.policy.gate_policy import GateDecided, PolicyFact
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols import DecisionGate

_TERMINAL_RATIONALE = "终态步：必须向用户收口；产物已从工作区账本合成摘要。"


class TerminalRespondGate(DecisionGate):
    """Force respond on last step for non-producing tool actions."""

    async def enforce(self, state: AgentState, decision: Decision) -> Decision:
        max_steps = state.budget.max_steps or 0
        reserve = TERMINAL_RESERVE_STEPS
        if state.step < max(0, max_steps - reserve):
            return decision
        if decision.action_type in {ActionType.RESPOND, ActionType.STOP, ActionType.ASK_HUMAN}:
            return decision
        evidence = build_delivery_evidence(state)
        if _is_producer(decision) and not evidence.satisfied:
            return decision

        response = synthesize_delivery_response(
            state,
            evidence,
            existing_text=decision.response_text or "",
        ) or "任务已完成。"
        forced = Decision(
            decision_id=decision.decision_id,
            action_type=ActionType.RESPOND,
            rationale=_TERMINAL_RATIONALE,
            confidence=decision.confidence,
            response_text=response,
        )
        record_gate_decided(
            state,
            GateDecided(
                event_id=new_id("gate"),
                gate="TerminalRespondGate",
                verdict="rewrite",
                is_rewritten=True,
                policy_fact=PolicyFact(
                    kind="terminal_respond",
                    message=_TERMINAL_RATIONALE,
                    source="terminal_respond",
                ),
            ),
        )
        return forced


def _is_producer(decision: Decision) -> bool:
    if decision.action_type != ActionType.USE_TOOL or not decision.tool_calls:
        return False
    return is_producer_tool(decision.tool_calls[0].tool_name)


__all__ = ["TerminalRespondGate"]
