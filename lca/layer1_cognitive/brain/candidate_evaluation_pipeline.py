"""CandidateEvaluationPipeline —— 候选评估的深度模块。

将 MAP 五步评估（decompose → predict → score → conflict check → arbitrate）
收敛为一个有深度的模块，对外只暴露 decompose + evaluate。

冲突检测逻辑（原 SimpleConflictMonitor 的 content-aware 比较）内联为
私有方法 _check_conflicts，不再需要独立的 ConflictMonitor 适配器。

当未来需要 LLM-based 评估时，只需替换 CandidateEvaluationPipeline 的实现。
"""

from __future__ import annotations

import structlog

from lca.contracts.decision import Decision
from lca.contracts.protocols import CandidateEvaluationPipeline, DecisionGate
from lca.contracts.semantic_keys import EVAL_CONFLICTS
from lca.contracts.state import AgentState

_log = structlog.get_logger("lca.candidate_evaluation_pipeline")


class SimpleCandidateEvaluationPipeline(CandidateEvaluationPipeline):
    """默认评估管线：内联所有 MAP 评估步骤。

    - decompose: 返回原始任务（不分解）
    - evaluate: predict → score → conflict check → arbitrate 全内联
    """

    async def decompose(self, state: AgentState) -> list[str]:
        return [state.task]

    async def evaluate(
        self,
        state: AgentState,
        candidates: list[Decision],
    ) -> Decision:
        conflicts = self._check_conflicts(candidates)
        best = max(candidates, key=lambda d: d.confidence)
        if conflicts:
            _log.warning("conflicts_detected", conflicts=conflicts)
            best.extra[EVAL_CONFLICTS] = conflicts
        return best

    @staticmethod
    def _check_conflicts(candidates: list[Decision]) -> list[str]:
        """Content-aware conflict detection among candidate decisions.

        Detects disagreements by comparing response text/rationale and action types.
        Returns conflict labels (e.g. ``content_disagreement``).
        """
        if len(candidates) < 2:
            return []
        texts = {
            (c.response_text or c.rationale or "").strip().lower()
            for c in candidates
            if (c.response_text or c.rationale)
        }
        if len(texts) > 1:
            return ["content_disagreement"]
        if len({c.action_type for c in candidates}) > 1:
            return ["action_type_disagreement"]
        return []


class GuardedCandidateEvaluationPipeline(CandidateEvaluationPipeline):
    """评估管线的装饰器：在 evaluate 结果上叠加 DecisionGate guardrail。

    开闭原则应用——不修改内层管线，只在外部包裹策略校验。
    """

    def __init__(
        self,
        inner: CandidateEvaluationPipeline,
        policy: DecisionGate,
    ) -> None:
        self._inner = inner
        self._policy = policy

    async def decompose(self, state: AgentState) -> list[str]:
        return await self._inner.decompose(state)

    async def evaluate(
        self,
        state: AgentState,
        candidates: list[Decision],
    ) -> Decision:
        decision = await self._inner.evaluate(state, candidates)
        return await self._policy.enforce(state, decision)
