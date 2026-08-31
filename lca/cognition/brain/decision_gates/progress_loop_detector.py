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

from lca.cognition.brain.decision_gates.chained import record_gate_decided
from lca.contracts.atoms.enums import ActionType
from lca.contracts.atoms.ids import new_id
from lca.contracts.models.core.decision import Decision, Turn
from lca.contracts.models.core.gate_policy import GateDecided, PolicyFact
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols import DecisionGate

_PROGRESS_WARNING_THRESHOLD = 3
_PROGRESS_BREAK_THRESHOLD = 6


class ProgressLoopDetector(DecisionGate):
    """Detect cross-tool loops with zero progress.

    Operates in two phases:
    1. Warning (at _PROGRESS_WARNING_THRESHOLD steps): emit a PolicyFact
       that the next ContextManifest will fold into the LLM prompt.
    2. Break (at _PROGRESS_BREAK_THRESHOLD steps): force RESPOND with
       diagnostic message including recent tool history.
    """

    async def enforce(self, state: AgentState, decision: Decision) -> Decision:
        if decision.action_type != ActionType.USE_TOOL or not decision.tool_calls:
            return decision

        count = self._count_consecutive_no_progress(state)
        if count < _PROGRESS_WARNING_THRESHOLD:
            return decision

        tools = self._recent_tool_history(state, n=count)
        tool_summary = ", ".join(tools)

        if count < _PROGRESS_BREAK_THRESHOLD:
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
    def _count_consecutive_no_progress(state: AgentState) -> int:
        """Count consecutive recent turns that produced no progress."""
        count = 0
        for turn in reversed(state.history):
            if not isinstance(turn, Turn):
                break
            if turn.decision.action_type != ActionType.USE_TOOL:
                break
            obs = turn.observation
            if obs is not None and obs.success:
                break
            count += 1
        return count

    @staticmethod
    def _recent_tool_history(state: AgentState, *, n: int) -> list[str]:
        """Return the last n tool names from history (oldest-first)."""
        tools: list[str] = []
        for turn in state.history:
            if not isinstance(turn, Turn):
                continue
            if turn.decision.action_type != ActionType.USE_TOOL:
                continue
            if not turn.decision.tool_calls:
                continue
            tools.append(turn.decision.tool_calls[0].tool_name)
        return tools[-n:] if n else []
