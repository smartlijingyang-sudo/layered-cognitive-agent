"""Synthesizer 默认实现 —— MoA 聚合层。"""

from __future__ import annotations

from lca.contracts.lifecycle import TaskStatus
from lca.contracts.protocols import Synthesizer
from lca.contracts.result import Result
from lca.contracts.state import Budget


class ConcatSynthesizer(Synthesizer):
    """简单拼接聚合：将所有候选结果的 output 用分隔符连接。

    最基础的 Synthesizer 实现，用于打底和测试。
    进阶实现（LLMSynthesizer）将调用 LLM 做 Layer-2 提炼。
    """

    def __init__(self, separator: str = "\n\n---\n\n") -> None:
        self._separator = separator

    async def synthesize(self, objective: str, candidates: list[Result]) -> Result:
        if not candidates:
            return Result.failed("No candidates to synthesize")

        outputs: list[str] = []
        total_steps = 0
        aggregated_budget = Budget()
        all_lessons: list[str] = []
        any_completed = False

        for i, candidate in enumerate(candidates):
            if candidate.output:
                outputs.append(f"[Candidate {i + 1}]\n{candidate.output}")
            total_steps += candidate.total_steps
            if candidate.budget_used is not None:
                aggregated_budget.used_tokens += candidate.budget_used.used_tokens
                aggregated_budget.used_cost_usd += candidate.budget_used.used_cost_usd
                aggregated_budget.used_steps += candidate.budget_used.used_steps
            all_lessons.extend(candidate.lessons)
            if candidate.status == TaskStatus.COMPLETED:
                any_completed = True

        synthesized_output = self._separator.join(outputs) if outputs else None

        return Result(
            trace_id=candidates[0].trace_id,
            status=TaskStatus.COMPLETED if any_completed else TaskStatus.FAILED,
            final_state_ref="",
            total_steps=total_steps,
            budget_used=aggregated_budget,
            output=synthesized_output,
            lessons=all_lessons,
            extra={"synthesis_method": "concat", "candidate_count": len(candidates)},
        )
