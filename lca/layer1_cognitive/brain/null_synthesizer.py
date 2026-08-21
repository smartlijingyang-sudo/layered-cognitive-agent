"""NullSynthesizer —— 宪法 §3.4 默认 no-op（ADR-0068）。

``NullSynthesizer.synthesize`` 返回 ``candidates[0]`` 若非空，否则
``Result.failed(...)``。不做拼接、不调用 LLM、不发事件。
"""

from __future__ import annotations

from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.result import Result
from lca.contracts.protocols import Synthesizer


class NullSynthesizer(Synthesizer):
    """Default null Synthesizer (ADR-0068 / 宪法 §3.4)."""

    async def synthesize(self, objective: str, candidates: list[Result]) -> Result:
        if not candidates:
            return Result.failed("No candidates to synthesize")
        return Result(
            trace_id=candidates[0].trace_id,
            status=TaskStatus.COMPLETED
            if candidates[0].status == TaskStatus.COMPLETED
            else TaskStatus.FAILED,
            final_state_ref="",
            total_steps=candidates[0].total_steps,
            budget_used=candidates[0].budget_used,
            output=candidates[0].output,
            lessons=candidates[0].lessons,
            extra={"synthesis_method": "null_passthrough", "candidate_count": len(candidates)},
        )


__all__ = ["NullSynthesizer"]
