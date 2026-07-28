"""DefaultStepOutcomePolicy —— 默认单步结果判定策略。

封装原 _loop / _should_stop 中散落的全部终止判定逻辑：
- respond 动作 → 提取 final_output + 判定是否停止
- handoff 动作 → 直接停止
- 降级成功（FALLBACK_DEGRADATION_KEY + success）→ 等价于 respond
- reflection verdict == needs_correction → 即使 respond 也不停止
- 预算耗尽 → 根据最后一步成功与否决定 completed / failed
"""

from __future__ import annotations

from lca.contracts.decision import Observation, Reflection, StructuredDecision
from lca.contracts.protocols import StepOutcome, StepOutcomePolicy
from lca.contracts.state import TypedState
from lca.layer2_runtime.fallback_handler import FALLBACK_DEGRADATION_KEY


class DefaultStepOutcomePolicy(StepOutcomePolicy):
    """框架内置的默认终止判定策略。

    识别"降级为 respond"的业务语义——这是该策略的职责，
    不是 Loop 的职责。
    """

    def resolve(
        self,
        state: TypedState,
        decision: StructuredDecision | None,
        observation: Observation | None,
        reflection: Reflection | None,
    ) -> StepOutcome:
        if decision is None or reflection is None:
            return StepOutcome()

        is_degraded_success = self._is_degraded_success(observation)

        if decision.action_type == "handoff":
            return StepOutcome(should_stop=True, status="completed")

        if decision.action_type == "respond" or is_degraded_success:
            final_output = decision.response_text if decision.response_text else None
            if final_output is None and is_degraded_success and observation is not None:
                payload = observation.payload
                if isinstance(payload, str):
                    final_output = payload
            should_stop = reflection.verdict != "needs_correction"
            return StepOutcome(
                should_stop=should_stop,
                final_output=final_output,
                status="completed" if should_stop else None,
            )

        return StepOutcome()

    @staticmethod
    def _is_degraded_success(observation: Observation | None) -> bool:
        """判断 observation 是否代表"降级成功"。"""
        if observation is None:
            return False
        return getattr(observation, "success", False) and FALLBACK_DEGRADATION_KEY in getattr(
            observation, "extra", {}
        )

    def resolve_budget_exceeded(
        self,
        observation: Observation | None,
        state: TypedState,
    ) -> StepOutcome:
        """预算耗尽时的特殊判定：最后一步成功则视为自然终止。"""
        last_ok = observation is not None and getattr(observation, "success", False)
        final_output: str | None = None
        if last_ok and "final_output" not in state.working_memory and observation is not None:
            payload = observation.payload
            if isinstance(payload, str):
                final_output = payload
        return StepOutcome(
            should_stop=True,
            final_output=final_output,
            status="completed" if last_ok else "failed",
        )
