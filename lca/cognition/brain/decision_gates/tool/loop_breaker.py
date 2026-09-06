"""Tool loop circuit breaker — stop repeated failing or stalled tool patterns.

The Gate sits in the Think plane and only rewrites a candidate Decision.  It
never executes a tool, mutates an external system, or changes graph topology.
The owning Gate plugin makes this policy profile-selectable.

A failed-call breaker alone is insufficient for an autonomous agent: a model can
consume an entire run by repeatedly issuing an idempotent, successful call that
returns the same observation.  The second branch therefore detects a consecutive
same-tool/same-arguments sequence whose normalized observations are identical.
It deliberately does not block polling-like calls whose observations change.
"""

from __future__ import annotations

from lca.cognition.brain.decision_gates.chained.chained import record_gate_decided
from lca.cognition.brain.decision_gates.loop.fingerprint import (
    tool_call_fingerprint,
    view_observation_fingerprint,
    view_tool_fingerprint,
)
from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.execution.decision import Decision, ToolCall
from lca.contracts.models.core.policy.gate_policy import GateDecided, PolicyFact
from lca.contracts.models.core.policy.loop_policy import DEFAULT_LOOP_POLICY
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols import DecisionGate
from lca.infrastructure.session.context.turn_control_reader import iter_control_turns_reversed

_BLOCKED_FAILURE_RATIONALE = (
    "同一工具已连续失败多次，禁止再次调用。请换用其他工具、修正代码，或直接 respond 收口。"
)
_BLOCKED_STALLED_RATIONALE = (
    "同一工具以相同参数连续返回相同结果，未观察到新进展，禁止继续重复调用。"
)


class ToolLoopBreakerGate(DecisionGate):
    """Block failed patterns and identical no-progress tool-call loops."""

    def __init__(self, *, thresholds=DEFAULT_LOOP_POLICY) -> None:
        self._thresholds = thresholds

    async def enforce(self, state: AgentState, decision: Decision) -> Decision:
        if decision.action_type != ActionType.USE_TOOL or not decision.tool_calls:
            return decision

        tool_call = decision.tool_calls[0]
        failure_count = self._consecutive_failures(state, tool_call.tool_name)
        if failure_count >= self._thresholds.break_failures:
            return self._block(
                state,
                decision,
                tool_call.tool_name,
                rationale=_BLOCKED_FAILURE_RATIONALE,
                response=self._failure_response(
                    tool_call.tool_name,
                    self._last_tool_error(state, tool_call.tool_name),
                ),
            )

        stalled_count = self._consecutive_identical_observations(state, tool_call)
        if stalled_count >= self._thresholds.break_stalled:
            return self._block(
                state,
                decision,
                tool_call.tool_name,
                rationale=_BLOCKED_STALLED_RATIONALE,
                response=(
                    f"{tool_call.tool_name} 以相同参数连续返回相同结果 "
                    f"{self._thresholds.break_stalled} 次，已停止重复调用。"
                ),
            )
        return decision

    def _block(
        self,
        state: AgentState,
        decision: Decision,
        tool_name: str,
        *,
        rationale: str,
        response: str,
    ) -> Decision:
        forced = self._force_respond(decision, rationale=rationale, response=response)
        record_gate_decided(
            state,
            GateDecided(
                event_id=new_id("gate"),
                gate="ToolLoopBreakerGate",
                verdict="rewrite",
                is_rewritten=True,
                tool_name=tool_name,
                rationale=rationale,
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
        """Count same-tool failures, preserving the established failure circuit breaker."""

        count = 0
        for turn in iter_control_turns_reversed(state):
            if turn.tool_name != tool_name:
                break
            if turn.observation_success:
                break
            count += 1
        return count

    @staticmethod
    def _consecutive_identical_observations(state: AgentState, candidate: ToolCall) -> int:
        """Count equivalent prior calls with an unchanged normalized observation.

        A return value of zero means the sequence contains an unknown/nonportable
        argument or result shape.  Failing open in that situation prevents a
        serialization edge case from turning a valid tool into an unexplainable
        hard stop; the independent failure breaker remains active.
        """

        candidate_fingerprint = tool_call_fingerprint(candidate)
        if candidate_fingerprint is None:
            return 0

        count = 0
        expected_observation: str | None = None
        for turn in iter_control_turns_reversed(state):
            if turn.tool_name != candidate.tool_name:
                break
            if view_tool_fingerprint(turn) != candidate_fingerprint:
                break
            observation_fingerprint = view_observation_fingerprint(turn)
            if observation_fingerprint is None:
                return 0
            if expected_observation is None:
                expected_observation = observation_fingerprint
            elif observation_fingerprint != expected_observation:
                break
            count += 1
        return count

    @staticmethod
    def _last_tool_error(state: AgentState, tool_name: str) -> str:
        """Return the latest same-tool error without leaking unrelated observations."""

        for turn in iter_control_turns_reversed(state):
            if turn.tool_name != tool_name:
                continue
            error = (turn.observation_error or "").strip()
            if error:
                return error
        return ""

    @staticmethod
    def _failure_response(tool_name: str, last_error: str) -> str:
        """Create a useful terminal response for the established failure condition."""

        if last_error:
            return (
                f"{tool_name} 连续失败 {DEFAULT_LOOP_POLICY.break_failures} 次，已停止重试。\n"
                f"最后错误：{last_error}"
            )
        return f"{tool_name} 连续失败 {DEFAULT_LOOP_POLICY.break_failures} 次，已停止重试。"

    @staticmethod
    def _force_respond(decision: Decision, *, rationale: str, response: str) -> Decision:
        """Preserve Decision identity while converting unsafe continuation into response."""

        return Decision(
            decision_id=decision.decision_id,
            action_type=ActionType.RESPOND,
            rationale=rationale,
            confidence=0.9,
            response_text=response,
            degraded_from=decision.action_type,
        )


__all__ = ["ToolLoopBreakerGate"]
