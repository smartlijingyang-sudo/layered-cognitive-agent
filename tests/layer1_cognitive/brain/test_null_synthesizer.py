"""NullSynthesizer —— ADR-0068 / 宪法 §3.4 默认 no-op。"""

import pytest

from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.result import Result
from lca.contracts.models.core.state import Budget
from lca.layer1_cognitive.brain.null_synthesizer import NullSynthesizer


@pytest.fixture()
def synth() -> NullSynthesizer:
    return NullSynthesizer()


@pytest.mark.asyncio
async def test_null_synthesizer_empty_candidates_fails(synth: NullSynthesizer) -> None:
    result = await synth.synthesize("stub-objective", [])
    assert result.status == TaskStatus.FAILED


@pytest.mark.asyncio
async def test_null_synthesizer_returns_first_candidate(synth: NullSynthesizer) -> None:
    c1 = Result(
        trace_id="t1",
        status=TaskStatus.COMPLETED,
        final_state_ref="",
        total_steps=2,
        budget_used=Budget(),
        output="first-output",
        lessons=[],
    )
    c2 = Result(
        trace_id="t2",
        status=TaskStatus.COMPLETED,
        final_state_ref="",
        total_steps=5,
        budget_used=Budget(),
        output="second-output",
        lessons=[],
    )
    result = await synth.synthesize("objective", [c1, c2])
    # Null 不做拼接：passthrough 第一个
    assert result.output == "first-output"
    assert result.trace_id == "t1"
    assert result.extra["synthesis_method"] == "null_passthrough"
    assert result.extra["candidate_count"] == 2
