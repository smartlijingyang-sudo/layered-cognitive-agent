"""Terminal respond gate — reserve last step for user-facing closure (ADR-0051)."""

from __future__ import annotations

from lca.contracts.atoms.enums import ActionType
from lca.contracts.models.core.budget import TERMINAL_RESERVE_STEPS
from lca.contracts.models.core.decision import Decision
from lca.contracts.models.core.state import AgentState
from lca.layer0_infra.workspace import get_run_workspace

_TERMINAL_RATIONALE = "终态步：必须向用户收口；产物已从工作区账本合成摘要。"


class TerminalRespondGate:
    """Force respond on terminal steps when LLM still selects a tool action."""

    async def enforce(self, state: AgentState, decision: Decision) -> Decision:
        max_steps = state.budget.max_steps or 0
        reserve = TERMINAL_RESERVE_STEPS
        if state.step < max(0, max_steps - reserve):
            return decision
        if decision.action_type in {ActionType.RESPOND, ActionType.STOP, ActionType.ASK_HUMAN}:
            return decision

        workspace = get_run_workspace()
        closure = workspace.artifacts.closure_text() if workspace is not None else ""
        response = closure or decision.response_text or "任务已完成。"
        return Decision(
            decision_id=decision.decision_id,
            action_type=ActionType.RESPOND,
            rationale=_TERMINAL_RATIONALE,
            confidence=decision.confidence,
            response_text=response,
        )
