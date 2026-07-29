"""CandidateEvaluationPipeline —— 将 MAP 四步评估收敛为一个有深度的模块。

通过构造函数注入 MAP 五模块（TaskDecomposer / StatePredictor / StateEvaluator /
ConflictMonitor / TaskCoordinator），对外只暴露 decompose + evaluate。
未注入时使用 trivial 默认实现（单候选场景保持链路完整）。

当未来需要 LLM-based 实现时，只需替换注入的模块实例。
"""

from __future__ import annotations

from typing import Any

import structlog

from lca.contracts.decision import StructuredDecision
from lca.contracts.protocols import (
    CandidateEvaluationPipeline,
    CompletionPolicy,
    ConflictMonitor,
    StateEvaluator,
    StatePredictor,
    TaskCoordinator,
    TaskDecomposer,
)
from lca.contracts.state import TypedState

_log = structlog.get_logger("lca.candidate_evaluation_pipeline")


class SimpleCandidateEvaluationPipeline(CandidateEvaluationPipeline):
    """默认评估管线：组合 MAP 模块。

    所有 MAP 模块均可选注入；未注入时使用 trivial 内联默认：
    - decompose: 返回原始任务（不分解）
    - predict: 以候选动作描述作为预期效果
    - score: 始终返回 1.0（单候选场景保持链路完整）
    - conflict check: 不检测冲突
    - arbitrate: 选择得分最高的候选方案
    """

    def __init__(
        self,
        decomposer: TaskDecomposer | None = None,
        predictor: StatePredictor | None = None,
        evaluator: StateEvaluator | None = None,
        conflict_monitor: ConflictMonitor | None = None,
        coordinator: TaskCoordinator | None = None,
    ) -> None:
        self._decomposer = decomposer
        self._predictor = predictor
        self._evaluator = evaluator
        self._conflict_monitor = conflict_monitor
        self._coordinator = coordinator

    async def decompose(self, state: TypedState) -> list[str]:
        if self._decomposer is not None:
            return await self._decomposer.decompose(state)
        return [state.task]

    async def evaluate(
        self,
        state: TypedState,
        candidates: list[StructuredDecision],
    ) -> StructuredDecision:
        predicted = [await self._predict(state, c.rationale) for c in candidates]
        scores = [await self._score(state, p) for p in predicted]
        conflicts = await self._check_conflicts(state, candidates)
        if conflicts:
            _log.warning("conflicts_detected", conflicts=conflicts)
        return await self._arbitrate(state, candidates, scores)

    async def _predict(self, state: TypedState, candidate_action: str) -> dict[str, Any]:
        if self._predictor is not None:
            return await self._predictor.predict(state, candidate_action)
        return {"expected_effect": candidate_action}

    async def _score(self, state: TypedState, predicted_state: dict[str, Any]) -> float:
        if self._evaluator is not None:
            return await self._evaluator.score(state, predicted_state)
        return 1.0

    async def _check_conflicts(
        self, state: TypedState, candidates: list[StructuredDecision]
    ) -> list[str]:
        if self._conflict_monitor is not None:
            return await self._conflict_monitor.check(state, candidates)
        return []

    async def _arbitrate(
        self,
        state: TypedState,
        candidates: list[StructuredDecision],
        scores: list[float],
    ) -> StructuredDecision:
        if self._coordinator is not None:
            return await self._coordinator.arbitrate(state, candidates, scores)
        best_idx = max(range(len(candidates)), key=lambda i: scores[i])
        return candidates[best_idx]


class GuardedCandidateEvaluationPipeline(CandidateEvaluationPipeline):
    """评估管线的装饰器：在 evaluate 结果上叠加 CompletionPolicy guardrail。

    开闭原则应用——不修改内层管线，只在外部包裹策略校验。
    """

    def __init__(
        self,
        inner: CandidateEvaluationPipeline,
        policy: CompletionPolicy,
    ) -> None:
        self._inner = inner
        self._policy = policy

    async def decompose(self, state: TypedState) -> list[str]:
        return await self._inner.decompose(state)

    async def evaluate(
        self,
        state: TypedState,
        candidates: list[StructuredDecision],
    ) -> StructuredDecision:
        decision = await self._inner.evaluate(state, candidates)
        return await self._policy.enforce(state, decision)
