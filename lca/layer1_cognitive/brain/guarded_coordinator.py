"""GuardedTaskCoordinator —— TaskCoordinator 的装饰器。

在内层 coordinator 返回候选决策后，叠加 CompletionPolicy 的确定性校验。
典型开闭原则应用：不改 SimpleTaskCoordinator 本体，只替换注入实例。
"""

from __future__ import annotations

from lca.contracts.decision import StructuredDecision
from lca.contracts.protocols import CompletionPolicy, TaskCoordinator
from lca.contracts.state import TypedState


class GuardedTaskCoordinator(TaskCoordinator):
    """在 inner coordinator 的仲裁结果上叠加 CompletionPolicy guardrail。"""

    def __init__(
        self,
        inner: TaskCoordinator,
        policy: CompletionPolicy,
    ) -> None:
        self._inner = inner
        self._policy = policy

    async def arbitrate(
        self,
        state: TypedState,
        candidates: list[StructuredDecision],
        scores: list[float],
    ) -> StructuredDecision:
        decision = await self._inner.arbitrate(state, candidates, scores)
        return await self._policy.enforce(state, decision)
