"""Tool loop circuit breaker — block repeated failing tool patterns (ADR-0051)."""

from __future__ import annotations

from lca.contracts.atoms.enums import ActionType
from lca.contracts.models.core.budget import TOOL_LOOP_BREAK_THRESHOLD
from lca.contracts.models.core.decision import Decision, Turn
from lca.contracts.models.core.state import AgentState

_BLOCKED_RATIONALE = (
    "同一工具已连续失败多次，禁止再次调用。请换用其他工具、修正代码，或直接 respond 收口。"
)


class ToolLoopBreakerGate:
    """Block a tool after consecutive failures of the same pattern."""

    async def enforce(self, state: AgentState, decision: Decision) -> Decision:
        if decision.action_type != ActionType.USE_TOOL or not decision.tool_calls:
            return decision

        tool_name = decision.tool_calls[0].tool_name
        if self._consecutive_failures(state, tool_name) >= TOOL_LOOP_BREAK_THRESHOLD:
            return self._force_respond(decision, state)
        return decision

    @staticmethod
    def _consecutive_failures(state: AgentState, tool_name: str) -> int:
        count = 0
        for turn in reversed(state.history):
            if not isinstance(turn, Turn):
                continue
            dec = turn.decision
            obs = turn.observation
            if dec.action_type != ActionType.USE_TOOL or not dec.tool_calls:
                break
            if dec.tool_calls[0].tool_name != tool_name:
                break
            if obs.success:
                break
            count += 1
        return count

    @staticmethod
    def _force_respond(decision: Decision, state: AgentState) -> Decision:
        from lca.layer0_infra.workspace import get_run_workspace

        workspace = get_run_workspace()
        closure = workspace.artifacts.closure_text() if workspace is not None else ""
        return Decision(
            decision_id=decision.decision_id,
            action_type=ActionType.RESPOND,
            rationale=_BLOCKED_RATIONALE,
            confidence=0.9,
            response_text=closure or state.final_output or "执行遇到问题，未能完成全部步骤。",
        )
