"""Multi-tool loop circuit breaker — wide-angle progress view (ADR-0214 PR-B).

Companion to :class:`ToolLoopBreakerGate`.  The single-tool breaker counts
consecutive same-tool failures and breaks on the third; a model that switches
between two tools while both fail slips through that count and consumes the
whole run.  This gate looks at *progress* across a sliding window instead of
*per-tool failure streaks*.

Three trigger conditions, evaluated in order:

1. ``TaskProgressProjection.is_stuck(window, threshold)`` — confidence
   declined more than ``threshold`` over the last ``window`` commits and
   ``completed`` did not grow.  This is the core signal: the model is
   observing no new information about the task.
2. ``completed_set_growth == 0`` over the last ``progress_break`` steps —
   progress has flatlined at the observation level even if confidence has
   not crashed.
3. ``fingerprint_variance == 0`` over the last ``window`` turns — the
   model is re-issuing the same tool call with the same observation; this
   is the classic polling loop the single-tool breaker misses because the
   tools alternate.

The gate sits in the Think plane and only rewrites a candidate Decision.
It never executes a tool, mutates an external system, or changes graph
topology.  The owning Gate plugin makes this policy profile-selectable
through :class:`LoopPolicyThresholds`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from lca.cognition.brain.decision_gates.chained.chained import record_gate_decided
from lca.cognition.brain.decision_gates.loop.fingerprint import (
    tool_call_fingerprint,
    view_tool_fingerprint,
)
from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.execution.decision import Decision, ToolCall
from lca.contracts.models.core.policy.gate_policy import GateDecided, PolicyFact
from lca.contracts.models.core.policy.loop_policy import (
    DEFAULT_LOOP_POLICY,
    LoopPolicyThresholds,
)
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols import DecisionGate
from lca.infrastructure.session.context.turn_control_reader import (
    ControlTurnView,
    iter_control_turns_reversed,
)
from lca.plugins.session.task_progress.projection import TaskProgressProjection

_BLOCKED_PROGRESS_RATIONALE = (
    "整体任务进度无进展：confidence 下降或 completed 不增长且工具调用出现"
    "重复指纹，熔断。请换策略、修正代码，或直接 respond 收口。"
)


@dataclass(frozen=True, slots=True)
class MultiToolBreakVerdict:
    """Diagnostic payload attached to the rewrite for downstream consumers.

    Filled by the gate before calling :meth:`DecisionGate` 's enforcement
    path; pure data, no I/O, no plugin side effects.  Stored on the gate
    decision via :class:`PolicyFact`.
    """

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
    """Discrete variance across the recent turn fingerprints.

    Returns a value in ``[0, 1]``: ``0.0`` when every recent turn produced
    the same normalized fingerprint as the candidate, ``1.0`` when every
    turn produced a distinct fingerprint.  ``None`` is treated as missing
    data and falls open to ``1.0`` so a serialization edge case does not
    silently hard-stop the agent.
    """

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
    ``window`` projection snapshots.  This requires projection to record
    per-snapshot completed sets; when unavailable, return ``window`` so the
    caller fails open (never falsely breaks a real-progress run).
    """

    snapshots = getattr(projection, "completed_history", None)
    if snapshots is None or len(snapshots) < 2:
        return window  # fail open

    recent = snapshots[-window:] if len(snapshots) >= window else list(snapshots)
    if len(recent) < 2:
        return window  # fail open

    growth = 0
    prev = recent[0]
    for snap in recent[1:]:
        growth += len(set(snap) - set(prev))
        prev = snap
    return growth


class MultiToolLoopBreakerGate(DecisionGate):
    """Wide-angle progress breaker — complement to ToolLoopBreakerGate.

    Trigger ladder (in order):

    1. ``confidence_delta < -stuck_threshold`` (over ``progress_break``
       steps) AND ``completed_growth == 0`` → break, kind=stuck_progress
    2. ``completed_growth == 0`` over ``progress_break`` steps → break,
       kind=completed_flatline (catches models that hold confidence flat
       while spinning wheels)
    3. ``fingerprint_variance == 0`` over ``progress_warn`` recent turns
       for the candidate tool → break, kind=fingerprint_static (catches
       the same-args-same-tool polling loop that single-tool breaker
       misses when alternating)

    All thresholds come from :class:`LoopPolicyThresholds` so the gate is
    profile-configurable.  The single-tool ``ToolLoopBreakerGate`` is kept
    as defense-in-depth; this gate is the primary line of defense for
    multi-tool patterns.
    """

    def __init__(
        self,
        *,
        thresholds: LoopPolicyThresholds = DEFAULT_LOOP_POLICY,
    ) -> None:
        self._thresholds = thresholds

    async def enforce(self, state: AgentState, decision: Decision) -> Decision:
        if decision.action_type != ActionType.USE_TOOL or not decision.tool_calls:
            return decision

        projection = self._resolve_projection(state)
        if projection is None:
            # C9 fail-open: projection missing means we cannot evaluate
            # progress; let single-tool breaker have its shot.
            return decision

        candidate = decision.tool_calls[0]

        # Layer 4 ladder (per LoopPolicyThresholds field docs).
        history = _confidence_history_from_projection(projection, self._thresholds.progress_break)
        confidence_delta = history[-1] - history[0] if len(history) >= 2 else 0.0
        growth = _completed_growth(projection, self._thresholds.progress_break)

        # ── Trigger 1: stuck progress ──────────────────────────────────
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

        # ── Trigger 2: completed flatline ──────────────────────────────
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

        # ── Trigger 3: static fingerprint across recent turns ───────────
        # iter_control_turns_reversed is a generator; materialize the first
        # ``progress_warn`` turns newest-first, then evaluate fingerprint
        # variance.  ``None`` fingerprint on either side fails open to 1.0.
        recent_turns: list[ControlTurnView] = []
        for turn in iter_control_turns_reversed(state):
            recent_turns.append(turn)
            if len(recent_turns) >= self._thresholds.progress_warn:
                break
        variance = _fingerprint_variance_over_turns(recent_turns, candidate)
        if len(recent_turns) >= self._thresholds.progress_warn and variance == 0.0:
            return self._block(
                state,
                decision,
                candidate.tool_name,
                rationale=_BLOCKED_PROGRESS_RATIONALE,
                verdict=MultiToolBreakVerdict(
                    kind="fingerprint_static",
                    window=self._thresholds.progress_warn,
                    confidence_delta=confidence_delta,
                    completed_growth=growth,
                    fingerprint_variance=variance,
                ),
                response=(
                    f"工具 {candidate.tool_name} 最近 "
                    f"{self._thresholds.progress_warn} 步指纹无变化, "
                    f"已熔断。"
                ),
            )

        return decision

    def _resolve_projection(self, state: AgentState) -> TaskProgressProjection | None:
        """Pull the bound projection off state, returning ``None`` when absent.

        Plugin wiring is added by the PR-B plugin (see
        ``lca/plugins/cognitive/gate/multi_tool_loop_breaker/plugin.py``).
        Until that plugin runs, the gate is a no-op — that is the fail-open
        path for C9.
        """

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
        # Stash the diagnostic verdict on the gate for the call-site
        # ``record_gate_decided`` to attach; kept as an attribute on the
        # forced decision so downstream tooling can introspect.
        object.__setattr__(forced, "_multi_tool_break_verdict", verdict)
        return forced


def _force_respond(decision: Decision, *, rationale: str, response: str) -> Decision:
    """Convert unsafe continuation into a RESPOND carrying the rationale.

    Mirrors :meth:`ToolLoopBreakerGate._force_respond` so the two breakers
    produce identical Decision shapes for downstream consumers.
    """

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
]
