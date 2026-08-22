"""DefaultStopRule —— 组合 StopOutcomePolicy + Budget 的默认终止裁判（PR5 纯函数化）。

L2 层职责：
    将原先散落在 CognitiveRuntime._loop 中的三种终止判定
    （budget 超限 / outcome 策略 / 异常状态）收敛为单一内聚类。

    v3 §5.1 + §17：本类为**纯函数**，禁止写入 ``state.final_output``
    或任何 AgentState 字段。最终输出由 Runtime 经 ``apply_stop`` 写入
    （PR5）。
"""

from __future__ import annotations

from lca.contracts.models.core.decision import Decision, Observation, Reflection
from lca.contracts.models.core.lifecycle import TaskStatus, coerce_status
from lca.contracts.models.core.state import AgentState
from lca.contracts.models.core.stop import StopDecision, StopReason
from lca.contracts.protocols import StopOutcomePolicy, StopRule


class DefaultStopRule(StopRule):
    """默认循环终止裁判（纯函数版）。

    不再直接写 ``state.final_output``；最终输出经 ``StopDecision.final_output``
    返回，由 Runtime 调用 ``reducer.apply_stop`` 写回 State。这是 v3 §5.1
    "StopRule 不得直接写 state.final_output" 的落地。
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

        # A response completed on the final permitted turn is a successful
        # outcome, not a budget failure.  Checking the outcome first also
        # preserves the terminal text for a one-step declarative profile.
        if outcome.should_stop:
            final_output = outcome.final_output if isinstance(outcome.final_output, str) else None
            return StopDecision(
                should_stop=True,
                reason=StopReason.TASK_COMPLETED,
                final_output=final_output,
                status=coerce_status(outcome.status) or TaskStatus.COMPLETED,
            )

        if state.budget.exceeded():
            return self._on_budget_exceeded(act_result, state)

        return StopDecision()

    def _on_budget_exceeded(
        self,
        observation: Observation | None,
        state: AgentState,
    ) -> StopDecision:
        budget_outcome = self._outcome_policy.resolve_budget_exceeded(observation, state)
        final_output = (
            budget_outcome.final_output if isinstance(budget_outcome.final_output, str) else None
        )
        return StopDecision(
            should_stop=True,
            reason=StopReason.BUDGET_EXCEEDED,
            final_output=final_output,
            status=coerce_status(budget_outcome.status) or TaskStatus.FAILED,
        )


__all__ = ["DefaultStopRule"]
