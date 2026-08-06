"""CandidateEvaluationPipeline —— 候选评估的默认实现。

将 MAP 五步评估（decompose → predict → score → conflict check → arbitrate）
收敛为单一 Protocol + 默认实现。

``SimpleCandidateEvaluationPipeline`` 是评估逻辑的单一事实源：
``ModularBrain`` 默认注入本实现（不再内联重复逻辑），自定义评估行为通过
整体替换 ``CandidateEvaluationPipeline`` 实现注入。
"""

from __future__ import annotations

import structlog

from lca.contracts.atoms.semantic_keys import EVAL_CONFLICTS
from lca.contracts.models.core.decision import Decision
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols import CandidateEvaluationPipeline

_log = structlog.get_logger("lca.candidate_evaluation_pipeline")


class SimpleCandidateEvaluationPipeline(CandidateEvaluationPipeline):
    """默认评估管线：内联所有 MAP 评估步骤。

    - decompose: 返回原始任务（不分解）
    - evaluate: conflict check + max confidence 选优
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
        """Content-aware conflict detection among candidate decisions."""
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
