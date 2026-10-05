"""Multi-tool loop circuit breaker and fingerprint helpers (ADR-0214 PR-B, ADR-0191 R7)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from lca.cognition.brain.decision_gates.chained import record_gate_decided
from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.execution.control_turn import ControlTurnView
from lca.contracts.models.core.execution.decision import Decision, ToolCall
from lca.contracts.models.core.execution.fingerprint import (
    fingerprint_payload,
    normalize_for_fingerprint,
    tool_call_fingerprint,
    view_tool_fingerprint,
)
from lca.contracts.models.core.policy.gate_policy import GateDecided, PolicyFact
from lca.contracts.models.core.policy.loop_policy import (
    DEFAULT_LOOP_POLICY,
    LoopPolicyThresholds,
)
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols import DecisionGate
from lca.infrastructure.session.context.turn_control_reader import (
    iter_control_turns_reversed,
)
from lca.plugins.session.task_progress.projection import TaskProgressProjection

_BLOCKED_PROGRESS_RATIONALE = (
    "整体任务进度无进展：confidence 下降或 completed 不增长且工具调用出现"
    "重复指纹，熔断。请换策略、修正代码，或直接 respond 收口。"
)


def view_observation_fingerprint(turn: ControlTurnView) -> str | None:
    payload = normalize_for_fingerprint(
        {
            "success": turn.observation_success,
            "payload": turn.observation_payload,
            "error": turn.observation_error,
        }
    )
    if payload is None:
        return None
    return fingerprint_payload(payload)


@dataclass(frozen=True, slots=True)
class MultiToolBreakVerdict:
    """Diagnostic payload attached to the rewrite for downstream consumers."""

    kind: str  # "stuck_progress" | "completed_flatline" | "fingerprint_static"
    window: int
    confidence_delta: float
    completed_growth: int
    fingerprint_variance: float


def _confidence_history_from_projection(
    projection: TaskProgressProjection,
    window: int,
) -> tuple[float, ...]:
    """Return the most recent ``window`` confidence values, oldest-first."""
    history = projection.confidence_history
    if len(history) <= window:
        return history
    return history[-window:]


def _fingerprint_variance_over_turns(
    turns: Sequence[ControlTurnView],
    candidate: ToolCall,
) -> float:
    """Discrete variance across the recent turn fingerprints."""
    candidate_fp = tool_call_fingerprint(candidate)
    if candidate_fp is None:
        return 1.0

    seen: set[str] = set()
    matched_candidate = 0
    total = 0
    for turn in turns:
        if turn.tool_name != candidate.tool_name:
            continue
        turn_fp = view_tool_fingerprint(turn)
        if turn_fp is None:
            return 1.0
        total += 1
        if turn_fp == candidate_fp:
            matched_candidate += 1
        seen.add(turn_fp)

    if total == 0:
        return 1.0
    return 1.0 - (matched_candidate / total)


def _completed_growth(
    projection: TaskProgressProjection,
    window: int,
) -> int:
    """Count how many unique completed step_ids were added across the last
    ``window`` projection snapshots.
    """
    snapshots = getattr(projection, "completed_history", None)
    if snapshots is None or len(snapshots) < 2:
        return window

    recent = snapshots[-window:] if len(snapshots) >= window else list(snapshots)
    if len(recent) < 2:
        return window

    growth = 0
    prev = recent[0]
    for snap in recent[1:]:
        growth += len(set(snap) - set(prev))
        prev = snap
    return growth


class MultiToolLoopBreakerGate(DecisionGate):
    """Wide-angle progress breaker — complement to ToolLoopBreakerGate."""

    def __init__(
        self,
        *,
        thresholds: LoopPolicyThresholds = DEFAULT_LOOP_POLICY,
    ) -> None:
        self._thresholds = thresholds

    async def enforce(self, state: AgentState, decision: Decision) -> Decision:
        if decision.action_type != ActionType.USE_TOOL or not decision.tool_calls:
            return decision

        candidate = decision.tool_calls[0]

        recent_turns: list[ControlTurnView] = []
        for turn in iter_control_turns_reversed(state):
            recent_turns.append(turn)
            if len(recent_turns) >= self._thresholds.consecutive_repeat_max:
                break
        variance = _fingerprint_variance_over_turns(recent_turns, candidate)
        if len(recent_turns) + 1 >= self._thresholds.consecutive_repeat_max and variance == 0.0:
            return self._block(
                state,
                decision,
                candidate.tool_name,
                rationale=_BLOCKED_PROGRESS_RATIONALE,
                verdict=MultiToolBreakVerdict(
                    kind="fingerprint_static",
                    window=self._thresholds.consecutive_repeat_max,
                    confidence_delta=0.0,
                    completed_growth=0,
                    fingerprint_variance=variance,
                ),
                response=(
                    f"工具 {candidate.tool_name} 连续 "
                    f"{self._thresholds.consecutive_repeat_max} 次相同指纹, "
                    f"已熔断。"
                ),
            )

        projection = self._resolve_projection(state)
        if projection is None:
            return decision

        history = _confidence_history_from_projection(projection, self._thresholds.progress_break)
        confidence_delta = history[-1] - history[0] if len(history) >= 2 else 0.0
        growth = _completed_growth(projection, self._thresholds.progress_break)

        # Trigger 1: stuck progress
        if (
            len(history) >= self._thresholds.progress_break
            and confidence_delta < -self._thresholds.progress_warn * 0.1
            and growth == 0
        ):
            return self._block(
                state,
                decision,
                candidate.tool_name,
                rationale=_BLOCKED_PROGRESS_RATIONALE,
                verdict=MultiToolBreakVerdict(
                    kind="stuck_progress",
                    window=self._thresholds.progress_break,
                    confidence_delta=confidence_delta,
                    completed_growth=growth,
                    fingerprint_variance=1.0,
                ),
                response=(
                    f"任务连续 {self._thresholds.progress_break} 步 confidence "
                    f"下降 {confidence_delta:+.2f}, completed 无新增, "
                    f"已熔断。"
                ),
            )

        # Trigger 2: completed flatline
        if len(history) >= self._thresholds.progress_break and growth == 0:
            return self._block(
                state,
                decision,
                candidate.tool_name,
                rationale=_BLOCKED_PROGRESS_RATIONALE,
                verdict=MultiToolBreakVerdict(
                    kind="completed_flatline",
                    window=self._thresholds.progress_break,
                    confidence_delta=confidence_delta,
                    completed_growth=growth,
                    fingerprint_variance=1.0,
                ),
                response=(
                    f"任务连续 {self._thresholds.progress_break} 步 completed 集合无新增, 已熔断。"
                ),
            )

        return decision

    def _resolve_projection(self, state: AgentState) -> TaskProgressProjection | None:
        return getattr(state, "task_progress_projection", None)

    def _block(
        self,
        state: AgentState,
        decision: Decision,
        tool_name: str,
        *,
        rationale: str,
        verdict: MultiToolBreakVerdict,
        response: str,
    ) -> Decision:
        forced = _force_respond(decision, rationale=rationale, response=response)
        record_gate_decided(
            state,
            GateDecided(
                event_id=new_id("gate"),
                gate="MultiToolLoopBreakerGate",
                verdict="rewrite",
                is_rewritten=True,
                tool_name=tool_name,
                rationale=rationale,
                policy_fact=PolicyFact(
                    kind="multi_tool_loop_break",
                    message=verdict.kind,
                    source="multi_tool_loop_breaker",
                ),
            ),
        )
        object.__setattr__(forced, "_multi_tool_break_verdict", verdict)
        return forced


def _force_respond(decision: Decision, *, rationale: str, response: str) -> Decision:
    return Decision(
        decision_id=decision.decision_id,
        action_type=ActionType.RESPOND,
        rationale=rationale,
        confidence=0.9,
        response_text=response,
        degraded_from=decision.action_type,
    )


__all__ = [
    "MultiToolBreakVerdict",
    "MultiToolLoopBreakerGate",
    "fingerprint_payload",
    "normalize_for_fingerprint",
    "tool_call_fingerprint",
    "view_observation_fingerprint",
    "view_tool_fingerprint",
]
