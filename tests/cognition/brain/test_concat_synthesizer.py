"""ConcatSynthesizer —— MoA 拼接聚合的直接用例。

run 链路（并行候选 → 合成）此前全仓只有 tests/scenario/parallel/test_parallel_synthesis.py
的场景级覆盖，synthesize() 自身的鲁棒分支（空候选、预算聚合、异常路径重抛）
0 直接用例。此处钉住。
"""

import pytest

import lca.cognition.brain.reasoner.synthesizer as synth_mod
from lca.cognition.brain.reasoner.synthesizer import ConcatSynthesizer
from lca.contracts.models.core.execution.result import Result
from lca.contracts.models.core.state.lifecycle import TaskStatus
from lca.contracts.models.core.state.state import Budget


@pytest.fixture()
def synth() -> ConcatSynthesizer:
    return ConcatSynthesizer()


@pytest.fixture()
def emit_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    calls: list[dict] = []

    def _recorder(**kwargs: object) -> None:
        calls.append(dict(kwargs))

    monkeypatch.setattr(synth_mod, "emit_synthesizer_merge_for_state", _recorder)
    return calls


def _candidate(
    trace_id: str = "t1",
    status: TaskStatus = TaskStatus.COMPLETED,
    output: str | None = "output",
    steps: int = 2,
    tokens: int = 10,
    cost: float = 0.01,
    budget_steps: int = 2,
    lessons: list[str] | None = None,
    budget: Budget | None = "default",  # type: ignore[assignment]
) -> Result:
    return Result(
        trace_id=trace_id,
        status=status,
        final_state_ref="",
        total_steps=steps,
        budget_used=(
            Budget(used_tokens=tokens, used_cost_usd=cost, used_steps=budget_steps)
            if budget == "default"
            else budget
        ),
        output=output,
        lessons=list(lessons or []),
    )


async def test_empty_candidates_returns_failed_result(
    synth: ConcatSynthesizer, emit_calls: list[dict]
) -> None:
    result = await synth.synthesize("stub-objective", [])

    assert result.status == TaskStatus.FAILED
    assert result.error == "No candidates to synthesize"
    assert result.total_steps == 0
    assert result.output is None
    # 空候选分支仍走 emit（当前实现记 outcome="success"，此处钉住行为本身）
    assert emit_calls == [
        {"state_id": "stub-objective", "candidate_count": 0, "outcome": "success"}
    ]


async def test_single_completed_candidate_output_tagged(
    synth: ConcatSynthesizer, emit_calls: list[dict]
) -> None:
    c1 = _candidate(trace_id="t1", output="hello", lessons=["l1"])

    result = await synth.synthesize("objective", [c1])

    assert result.status == TaskStatus.COMPLETED
    assert result.trace_id == "t1"
    assert result.output == "[Candidate 1]\nhello"
    assert result.total_steps == 2
    assert result.lessons == ["l1"]
    assert result.final_state_ref == ""
    assert result.extra["synthesis_method"] == "concat"
    assert result.extra["candidate_count"] == 1
    # 返回的是新 Result，不是候选对象本身
    assert result is not c1
    assert emit_calls == [{"state_id": "t1", "candidate_count": 1, "outcome": "success"}]


async def test_mixed_status_any_completed_wins(synth: ConcatSynthesizer) -> None:
    c1 = _candidate(trace_id="t1", status=TaskStatus.FAILED, output="bad")
    c2 = _candidate(trace_id="t2", status=TaskStatus.COMPLETED, output="good")

    result = await synth.synthesize("objective", [c1, c2])

    assert result.status == TaskStatus.COMPLETED
    assert result.output == "[Candidate 1]\nbad\n\n---\n\n[Candidate 2]\ngood"


async def test_all_failed_still_joins_outputs(synth: ConcatSynthesizer) -> None:
    c1 = _candidate(trace_id="t1", status=TaskStatus.FAILED, output="bad1")
    c2 = _candidate(trace_id="t2", status=TaskStatus.FAILED, output="bad2")

    result = await synth.synthesize("objective", [c1, c2])

    assert result.status == TaskStatus.FAILED
    assert result.output == "[Candidate 1]\nbad1\n\n---\n\n[Candidate 2]\nbad2"
    assert result.extra["candidate_count"] == 2


async def test_budget_aggregation_skips_none_and_sums(
    synth: ConcatSynthesizer,
) -> None:
    c1 = _candidate(trace_id="t1", tokens=100, cost=0.5, budget_steps=3, steps=3)
    c2 = _candidate(trace_id="t2", tokens=0, cost=0.0, budget_steps=0, steps=5, budget=None)

    result = await synth.synthesize("objective", [c1, c2])

    assert result.total_steps == 8
    assert result.budget_used.used_tokens == 100
    assert result.budget_used.used_cost_usd == pytest.approx(0.5)
    assert result.budget_used.used_steps == 3


async def test_all_empty_outputs_yields_none_output(
    synth: ConcatSynthesizer,
) -> None:
    c1 = _candidate(trace_id="t1", output=None)
    c2 = _candidate(trace_id="t2", output="")

    result = await synth.synthesize("objective", [c1, c2])

    assert result.status == TaskStatus.COMPLETED
    assert result.output is None


async def test_lessons_concatenated_in_order(synth: ConcatSynthesizer) -> None:
    c1 = _candidate(trace_id="t1", lessons=["a", "b"])
    c2 = _candidate(trace_id="t2", lessons=["c"])

    result = await synth.synthesize("objective", [c1, c2])

    assert result.lessons == ["a", "b", "c"]


async def test_custom_separator() -> None:
    synth = ConcatSynthesizer(separator=" | ")

    result = await synth.synthesize(
        "objective",
        [_candidate(trace_id="t1", output="one"), _candidate(trace_id="t2", output="two")],
    )

    assert result.output == "[Candidate 1]\none | [Candidate 2]\ntwo"


async def test_exception_path_emits_failure_and_reraises(
    synth: ConcatSynthesizer, emit_calls: list[dict]
) -> None:
    class _ExplodingCandidate:
        trace_id = "boom"

        @property
        def output(self) -> str:
            raise KeyboardInterrupt("simulated")

    with pytest.raises(KeyboardInterrupt):
        await synth.synthesize("objective", [_ExplodingCandidate()])  # type: ignore[list-item]

    # 异常路径记 outcome="failure"，重抛不被吞
    assert emit_calls == [{"state_id": "boom", "candidate_count": 1, "outcome": "failure"}]


async def test_emit_exception_does_not_break_synthesis(
    synth: ConcatSynthesizer, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(**_: object) -> None:
        raise RuntimeError("spine down")

    monkeypatch.setattr(synth_mod, "emit_synthesizer_merge_for_state", _boom)

    result = await synth.synthesize("objective", [_candidate(trace_id="t1")])

    # emit 抛错被 contextlib.suppress 吞掉，合成结果不受影响
    assert result.status == TaskStatus.COMPLETED
    assert result.output == "[Candidate 1]\noutput"
