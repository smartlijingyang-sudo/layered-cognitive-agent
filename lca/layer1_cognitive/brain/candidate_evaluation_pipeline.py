"""CandidateEvaluationPipeline —— 将 MAP 四步评估收敛为一个有深度的模块。

把 TaskDecomposer / StatePredictor / StateEvaluator / ConflictMonitor /
TaskCoordinator 的默认实现内联为私有方法，对外只暴露 decompose + evaluate。
当未来需要 LLM-based 实现时，可沿内部 seams 逐步替换。
"""

from __future__ import annotations

from typing import Any

import structlog

from lca.contracts.decision import StructuredDecision
from lca.contracts.protocols import (
    CandidateEvaluationPipeline,
    CompletionPolicy,
)
from lca.contracts.state import TypedState

_log = structlog.get_logger("lca.candidate_evaluation_pipeline")


class SimpleCandidateEvaluationPipeline(CandidateEvaluationPipeline):
    """默认评估管线：内联四步 MAP 评估逻辑。

    - decompose: 返回原始任务（不分解）
    - predict: 以候选动作描述作为预期效果
    - score: 始终返回 1.0（单候选场景保持链路完整）
    - conflict check: 不检测冲突
    - arbitrate: 选择得分最高的候选方案
    """

    async def decompose(self, state: TypedState) -> list[str]:
        return [state.task]

    async def evaluate(
        self,
        state: TypedState,
        candidates: list[StructuredDecision],
    ) -> StructuredDecision:
        predicted = [self._predict(c.rationale) for c in candidates]
        scores = [self._score(p) for p in predicted]
        conflicts = self._check_conflicts(state, candidates)
        if conflicts:
            _log.warning("conflicts_detected", conflicts=conflicts)
        return self._arbitrate(candidates, scores)

    @staticmethod
    def _predict(candidate_action: str) -> dict[str, Any]:
        return {"expected_effect": candidate_action}

    @staticmethod
    def _score(predicted_state: dict[str, Any]) -> float:
        return 1.0

    @staticmethod
    def _check_conflicts(state: TypedState, candidates: list[StructuredDecision]) -> list[str]:
        return []

    @staticmethod
    def _arbitrate(candidates: list[StructuredDecision], scores: list[float]) -> StructuredDecision:
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
