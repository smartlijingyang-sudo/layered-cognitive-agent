"""Tool loop circuit breaker — block repeated failing tool patterns (ADR-0051).

PR4: rewrite / deny verdicts MUST call ``record_gate_decided``.  Allow
verdicts MUST NOT (per spec §3.5).

Forced respond is a *failure* closure. It must carry the last tool error.
It must not reuse artifact "generated files" copy, which is a success manifest.
"""

from __future__ import annotations

from lca.contracts.atoms.enums import ActionType
from lca.contracts.atoms.ids import new_id
from lca.contracts.models.core.budget import TOOL_LOOP_BREAK_THRESHOLD
from lca.contracts.models.core.decision import Decision, Turn
from lca.contracts.models.core.gate_policy import GateDecided, PolicyFact
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols import DecisionGate
from lca.layer1_cognitive.brain.decision_gates.chained import record_gate_decided

_BLOCKED_RATIONALE = (
    "同一工具已连续失败多次，禁止再次调用。请换用其他工具、修正代码，或直接 respond 收口。"
)


class ToolLoopBreakerGate(DecisionGate):
    """Block a tool after consecutive failures of the same pattern."""

    async def enforce(self, state: AgentState, decision: Decision) -> Decision:
        if decision.action_type != ActionType.USE_TOOL or not decision.tool_calls:
            return decision

        tool_name = decision.tool_calls[0].tool_name
        if self._consecutive_failures(state, tool_name) < TOOL_LOOP_BREAK_THRESHOLD:
            return decision
        forced = self._force_respond(decision, tool_name, self._last_tool_error(state, tool_name))
        record_gate_decided(
            state,
            GateDecided(
                event_id=new_id("gate"),
                gate="ToolLoopBreakerGate",
                verdict="rewrite",
                is_rewritten=True,
                tool_name=tool_name,
                rationale=_BLOCKED_RATIONALE,
                policy_fact=PolicyFact(
                    kind="tool_loop_break",
                    message=forced.response_text or "",
                    source="tool_loop_breaker",
                ),
            ),
        )
        return forced

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
    def _last_tool_error(state: AgentState, tool_name: str) -> str:
        for turn in reversed(state.history):
            if not isinstance(turn, Turn):
                continue
            dec = turn.decision
            if dec.action_type != ActionType.USE_TOOL or not dec.tool_calls:
                continue
            if dec.tool_calls[0].tool_name != tool_name:
                continue
            err = (turn.observation.error or "").strip()
            if err:
                return err
        return ""

    @classmethod
    def _force_respond(cls, decision: Decision, tool_name: str, last_error: str) -> Decision:
        n = TOOL_LOOP_BREAK_THRESHOLD
        if last_error:
            text = f"{tool_name} 连续失败 {n} 次，已停止重试。\n最后错误：{last_error}"
        else:
            text = f"{tool_name} 连续失败 {n} 次，已停止重试。"
        return Decision(
            decision_id=decision.decision_id,
            action_type=ActionType.RESPOND,
            rationale=_BLOCKED_RATIONALE,
            confidence=0.9,
            response_text=text,
        )
