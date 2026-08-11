"""DefaultStopOutcomePolicy —— 默认单步结果判定策略。

L2 层职责：
    根据当前 step 的 decision / observation / reflection 判定：
    - 是否应停止循环（should_stop）
    - 最终输出（final_output）
    - 任务状态（status）

    与 StopRule 组合使用：StopRule 负责 budget 检查 + 调用本策略，
    本策略只负责业务语义的判定（action_type、reflection_verdict）。
"""

from __future__ import annotations

from lca.contracts.atoms.enums import ActionType, ReflectionVerdict
from lca.contracts.models.core.decision import Decision, Observation, Reflection
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols import StopOutcome, StopOutcomePolicy
from lca.layer2_runtime.completion.artifact_closure import synthesize_artifact_closure

# Consecutive tool failures before a respond → likely false completion.
# Following LobeHub's forceFinish pattern: don't accept "done" when the
# agent actually failed to produce anything.
_FALSE_COMPLETION_WINDOW = 3


class DefaultStopOutcomePolicy(StopOutcomePolicy):
    """默认单步结果判定策略。

    判定规则：
    - HANDOFF 动作 → 立即停止（COMPLETED）
    - RESPOND 动作或降级成功 → 提取 final_output，
      除非 reflection 判定 NEEDS_CORRECTION 则继续循环
    - RESPOND 但近期工具连续失败 → 视为虚假完成，继续循环
    - 其他 → 继续循环
    """

    def resolve(
        self,
        state: AgentState,
        decision: Decision | None,
        observation: Observation | None,
        reflection: Reflection | None,
    ) -> StopOutcome:
        if decision is None or reflection is None:
            return StopOutcome()
        degraded_ok = bool(
            observation is not None and observation.success and observation.degraded_from
        )
        if decision.action_type == ActionType.HANDOFF:
            return StopOutcome(should_stop=True, status=TaskStatus.COMPLETED)
        if decision.action_type == ActionType.RESPOND or degraded_ok:
            final_output = decision.response_text if decision.response_text else None
            if (
                final_output is None
                and degraded_ok
                and observation is not None
                and isinstance(observation.payload, str)
            ):
                final_output = observation.payload
            should_stop = reflection.verdict != ReflectionVerdict.NEEDS_CORRECTION
            # False-completion guard: if the model says "done" but the last N
            # tool calls all failed, it's giving up — not completing.
            if should_stop and _recent_tool_failures(state) >= _FALSE_COMPLETION_WINDOW:
                should_stop = False
            return StopOutcome(
                should_stop=should_stop,
                final_output=final_output,
                status=TaskStatus.COMPLETED if should_stop else None,
            )
        return StopOutcome()

    def resolve_budget_exceeded(
        self, observation: Observation | None, state: AgentState
    ) -> StopOutcome:
        last_ok = observation is not None and observation.success
        final_output = synthesize_artifact_closure()
        if (
            final_output is None
            and last_ok
            and state.final_output is None
            and observation is not None
            and isinstance(observation.payload, str)
        ):
            final_output = observation.payload
        status = TaskStatus.COMPLETED if (last_ok or final_output) else TaskStatus.FAILED
        return StopOutcome(
            should_stop=True,
            final_output=final_output,
            status=status,
        )


def _recent_tool_failures(state: AgentState) -> int:
    """Count consecutive failed tool calls at the tail of history.

    Only counts USE_TOOL turns — stops counting at the first non-tool turn
    (e.g. a prior respond or delegate).
    """
    failures = 0
    for turn in reversed(state.history):
        if turn.decision.action_type != ActionType.USE_TOOL:
            break
        if turn.observation is not None and not turn.observation.success:
            failures += 1
    return failures
