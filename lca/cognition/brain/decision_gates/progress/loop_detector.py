"""ProgressLoopDetector — detect multi-tool loops with no meaningful progress.

PR4: warning + break phases record GateDecided events.  The warning
phase no longer writes to ``state.working_memory[\"loop_warning\"]`` —
the spec forbids that path.  The PolicyFact is folded into the next
ContextManifest.

Unlike ToolLoopBreakerGate which only blocks a *single* tool after repeated
failures, this gate detects the broader pattern:

    writeFile → runCommand → (fails) → readFile → writeFile → runCommand → …

Here no single tool repeats enough to trigger ToolLoopBreakerGate, yet the
agent is clearly stuck in a cross-tool cycle producing nothing.

Detection strategy:
    Track the number of consecutive steps that produced NO progress:
    - No observation.success == True
    - No output_text was generated
    - No artifact was harvested into the workspace

When the count exceeds the threshold, force a respond with a diagnostic
message that includes the recent tool call history.

ADR reference: zero-delivery root-cause #2 (multi-tool loop detection).
"""

from __future__ import annotations

from lca.cognition.brain.decision_gates.chained.chained import record_gate_decided
from lca.cognition.convergence.evidence import build_delivery_evidence
from lca.cognition.convergence.payload import turn_has_delivery_signal
from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.models.core.policy.gate_policy import GateDecided, PolicyFact
from lca.contracts.models.core.policy.loop_policy import (
    DEFAULT_LOOP_POLICY,
    LoopPolicyThresholds,
)
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols import DecisionGate
from lca.infrastructure.session.context.turn_control_reader import (
    ControlTurnView,
    control_turns,
    iter_control_turns_reversed,
)


class ProgressLoopDetector(DecisionGate):
    """Detect cross-tool loops with zero progress.

    Operates in two phases:
    1. Warning (at progress_warn steps): emit a PolicyFact
       that the next ContextManifest will fold into the LLM prompt.
    2. Break (at progress_break steps): force RESPOND with
       diagnostic message including recent tool history.
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

        count = max(
            self._count_consecutive_no_progress(state),
            self._count_producer_stall_after_delivery(state),
        )
        if count < self._thresholds.progress_warn:
            return decision

        tools = self._recent_tool_history(state, n=count)
        tool_summary = ", ".join(tools)

        if count < self._thresholds.progress_break:
            # Phase 1: emit PolicyFact for next think phase.
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
                        source="progress_loop",
                    ),
                ),
            )
            return decision

        # Phase 2: force respond with diagnostics.
        text = (
            f"连续 {count} 步未产生有效输出，已停止重试。\n"
            f"最近尝试的工具: {tool_summary}。\n"
            f"建议: 检查工具参数是否正确，或换一种方法完成任务。"
        )
        forced = Decision(
            decision_id=decision.decision_id,
            action_type=ActionType.RESPOND,
            rationale="无进展循环检测：Agent 连续多步未产出有效内容，强制收口。",
            confidence=0.9,
            response_text=text,
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
                    message=text,
                    source="progress_loop",
                ),
            ),
        )
        return forced

    @staticmethod
    def _count_producer_stall_after_delivery(state: AgentState) -> int:
        """Count successful tool turns after delivery already satisfied (ADR-0196)."""
        if not build_delivery_evidence(state).satisfied:
            return 0
        count = 0
        for turn in iter_control_turns_reversed(state):
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
        for turn in iter_control_turns_reversed(state):
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
        for turn in control_turns(state):
            if turn.action_type != ActionType.USE_TOOL:
                continue
            if not turn.tool_name:
                continue
            tools.append(turn.tool_name)
        return tools[-n:] if n else []
