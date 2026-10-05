"""Loop circuit breakers and progress detectors (ADR-0191, ADR-0214).

Contains:
- ToolLoopBreakerGate: Circuit breaker for repeated failing or stalled tool patterns.
- ProgressLoopDetector: Multi-tool loop detector for cross-tool cycles with no progress.
"""

from __future__ import annotations

from lca.cognition.brain.decision_gates.chained import record_gate_decided
from lca.cognition.brain.decision_gates.multi_tool_loop import (
    tool_call_fingerprint,
    view_observation_fingerprint,
    view_tool_fingerprint,
)
from lca.cognition.convergence.evidence import build_delivery_evidence
from lca.cognition.convergence.payload import (
    observation_files_created,
    turn_has_delivery_signal,
)
from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.execution.control_turn import ControlTurnView
from lca.contracts.models.core.execution.decision import Decision, ToolCall
from lca.contracts.models.core.policy.gate_policy import GateDecided, PolicyFact
from lca.contracts.models.core.policy.loop_policy import (
    DEFAULT_LOOP_POLICY,
    LoopPolicyThresholds,
)
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols import DecisionGate
from lca.infrastructure.session.context.turn_control_reader import (
    control_turns,
    iter_control_turns_reversed,
)

_BLOCKED_FAILURE_RATIONALE = (
    "同一工具已连续失败多次，禁止再次调用。请换用其他工具、修正代码，或直接 respond 收口。"
)
_BLOCKED_STALLED_RATIONALE = (
    "同一工具以相同参数连续返回相同结果，未观察到新进展，禁止继续重复调用。"
)


class ToolLoopBreakerGate(DecisionGate):
    """Block failed patterns and identical no-progress tool-call loops."""

    def __init__(
        self,
        *,
        thresholds: LoopPolicyThresholds = DEFAULT_LOOP_POLICY,
    ) -> None:
        self._thresholds = thresholds

    async def enforce(self, state: AgentState, decision: Decision) -> Decision:
        if decision.action_type != ActionType.USE_TOOL or not decision.tool_calls:
            return decision

        tool_call = decision.tool_calls[0]
        failure_count = self._consecutive_failures(state, tool_call.tool_name)
        last_error = self._last_tool_error(state, tool_call.tool_name)
        wire_repeat_limit = 2
        if failure_count >= self._thresholds.break_failures or (
            failure_count >= wire_repeat_limit and last_error.startswith("tool_wire")
        ):
            return self._block(
                state,
                decision,
                tool_call.tool_name,
                rationale=_BLOCKED_FAILURE_RATIONALE,
                response=self._failure_response(
                    tool_call.tool_name,
                    last_error,
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
        for turn in iter_control_turns_reversed(state):
            if turn.tool_name != tool_name:
                continue
            error = (turn.observation_error or "").strip()
            if error:
                return error
        return ""

    def _failure_response(self, tool_name: str, last_error: str) -> str:
        limit = self._thresholds.break_failures
        if last_error:
            return f"{tool_name} 连续失败 {limit} 次，已停止重试。\n最后错误：{last_error}"
        return f"{tool_name} 连续失败 {limit} 次，已停止重试。"

    @staticmethod
    def _force_respond(decision: Decision, *, rationale: str, response: str) -> Decision:
        return Decision(
            decision_id=decision.decision_id,
            action_type=ActionType.RESPOND,
            rationale=rationale,
            confidence=0.9,
            response_text=response,
            degraded_from=decision.action_type,
        )


class ProgressLoopDetector(DecisionGate):
    """Detect cross-tool loops with zero progress."""

    def __init__(
        self,
        *,
        thresholds: LoopPolicyThresholds = DEFAULT_LOOP_POLICY,
    ) -> None:
        self._thresholds = thresholds

    async def enforce(self, state: AgentState, decision: Decision) -> Decision:
        if decision.action_type != ActionType.USE_TOOL or not decision.tool_calls:
            return decision

        count = max(
            self._count_consecutive_no_progress(state),
            self._count_producer_stall_after_delivery(state),
        )
        if count < self._thresholds.progress_warn:
            return decision

        tools = self._recent_tool_history(state, n=count)
        tool_summary = ", ".join(tools)

        if count < self._thresholds.progress_break:
            message = (
                f"⚠️ 你已连续 {count} 步没有产生有效输出。"
                f"最近尝试的工具: {tool_summary}。"
                f"请换一种方法，或直接 respond 回复用户。"
            )
            record_gate_decided(
                state,
                GateDecided(
                    event_id=new_id("gate"),
                    gate="ProgressLoopDetector",
                    verdict="warn",
                    is_rewritten=False,
                    policy_fact=PolicyFact(
                        kind="progress_loop_warning",
                        message=message,
                        source="progress_loop_detector",
                    ),
                ),
            )
            return decision

        message = (
            f"已连续 {count} 步没有产生有效进展（最近工具: {tool_summary}），"
            f"已自动终止重试并收口。请直接向用户说明当前情况。"
        )
        record_gate_decided(
            state,
            GateDecided(
                event_id=new_id("gate"),
                gate="ProgressLoopDetector",
                verdict="rewrite",
                is_rewritten=True,
                policy_fact=PolicyFact(
                    kind="progress_loop_break",
                    message=message,
                    source="progress_loop_detector",
                ),
            ),
        )
        return Decision(
            decision_id=decision.decision_id,
            action_type=ActionType.RESPOND,
            rationale="多工具循环检测触发：连续无有效输出步数超限，强制收尾",
            confidence=0.9,
            response_text=message,
            degraded_from=decision.action_type,
        )

    @staticmethod
    def _count_producer_stall_after_delivery(state: AgentState) -> int:
        """Count successful tool turns after delivery already satisfied (ADR-0196)."""
        if not build_delivery_evidence(state).satisfied:
            return 0
        count = 0
        for turn in iter_control_turns_reversed(state, files_created_fn=observation_files_created):
            if turn.action_type != ActionType.USE_TOOL:
                break
            if not turn.observation_success:
                break
            count += 1
        return max(0, count - 1)

    @staticmethod
    def _turn_has_meaningful_progress(turn: ControlTurnView) -> bool:
        return turn_has_delivery_signal(
            turn.observation_payload,
            files_created=turn.files_created,
        )

    @staticmethod
    def _count_consecutive_no_progress(state: AgentState) -> int:
        """Count consecutive recent turns that produced no progress."""
        count = 0
        for turn in iter_control_turns_reversed(state, files_created_fn=observation_files_created):
            if turn.action_type != ActionType.USE_TOOL:
                break
            if ProgressLoopDetector._turn_has_meaningful_progress(turn):
                break
            count += 1
        return count

    @staticmethod
    def _recent_tool_history(state: AgentState, *, n: int) -> list[str]:
        """Return the last n tool names from control turns (oldest-first)."""
        tools: list[str] = []
        for turn in control_turns(state, files_created_fn=observation_files_created):
            if turn.action_type != ActionType.USE_TOOL:
                continue
            if not turn.tool_name:
                continue
            tools.append(turn.tool_name)
        return tools[-n:] if n else []


__all__ = ["ProgressLoopDetector", "ToolLoopBreakerGate"]
