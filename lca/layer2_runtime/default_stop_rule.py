"""DefaultStopRule —— 组合 StopOutcomePolicy + Budget 的默认终止裁判。

L2 层职责：
    将原先散落在 CognitiveRuntime._loop 中的三种终止判定
    （budget 超限 / outcome 策略 / 异常状态）收敛为单一内聚类。

    判定流程：
    1. 调用 StopOutcomePolicy.resolve() 获取业务判定
    2. 检查 budget 是否超限（资源约束）
    3. 综合输出 StopDecision
"""

from __future__ import annotations

from lca.contracts.models.core.decision import Decision, Observation, Reflection
from lca.contracts.models.core.lifecycle import TaskStatus, coerce_status
from lca.contracts.models.core.state import AgentState
from lca.contracts.models.core.stop import StopDecision, StopReason
from lca.contracts.protocols import StopOutcomePolicy, StopRule


class DefaultStopRule(StopRule):
    """默认循环终止裁判。

    组合 StopOutcomePolicy（业务判定）与 Budget 检查（资源约束），
    输出统一的 StopDecision。
    """

    def __init__(self, outcome_policy: StopOutcomePolicy) -> None:
        self._outcome_policy = outcome_policy

    def decide(
        self,
        state: AgentState,
        decision: Decision | None,
        act_result: Observation | None,
        reflection: Reflection | None,
    ) -> StopDecision:
        outcome = self._outcome_policy.resolve(state, decision, act_result, reflection)
        if outcome.final_output is not None:
            state.final_output = outcome.final_output

        if state.budget.exceeded():
            return self._on_budget_exceeded(act_result, state)

        if outcome.should_stop:
            return StopDecision(
                should_stop=True,
                reason=StopReason.TASK_COMPLETED,
                final_output=state.final_output if isinstance(state.final_output, str) else None,
                status=coerce_status(outcome.status) or TaskStatus.COMPLETED,
            )

        return StopDecision()

    def _on_budget_exceeded(
        self,
        observation: Observation | None,
        state: AgentState,
    ) -> StopDecision:
        budget_outcome = self._outcome_policy.resolve_budget_exceeded(observation, state)
        if budget_outcome.final_output is not None:
            state.final_output = budget_outcome.final_output
        return StopDecision(
            should_stop=True,
            reason=StopReason.BUDGET_EXCEEDED,
            final_output=state.final_output if isinstance(state.final_output, str) else None,
            status=coerce_status(budget_outcome.status) or TaskStatus.FAILED,
        )


__all__ = ["DefaultStopRule"]
