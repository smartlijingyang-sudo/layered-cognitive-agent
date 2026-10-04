"""Tests for phase.think.context.summarize (ADR-0283).

Sediment-before-compact + structured summary. The node shares the
0.7 soft gate with truncate; past the gate it sediments the doomed head
region through the memory write path BEFORE summarizing, and fail-closes
to ``truncate_oldest`` when sediment cannot run or cannot persist.

Acceptance mapping (ADR-0283 §4):
- T1: writer raises ⇒ no summarize (degrade, honestly labeled).
- T2: no writer + candidates ⇒ degrade to truncate_oldest, sedimented=0.
- T3: fixtures with planted facts ⇒ 100% retention in CompactSummary,
  noise in ``dropped``, provenance ``source="compaction"`` on writes.
- T4: ``SUMMARIZE_PROMPT_VERSION`` matches the prompt file marker.
"""

from __future__ import annotations

from typing import Any

import pytest

from lca.contracts.atoms.ids.ids import utc_now
from lca.contracts.dto.compact_receipt import CompactReceipt
from lca.contracts.dto.compact_summary import CompactSummary
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.nodes.think.context.sediment import (
    AssistantMemorySedimentWriter,
    SedimentCandidate,
    extract_sediment_candidates,
    sediment_writer_scope,
)
from lca.nodes.think.context.summarize import (
    SUMMARIZE_PROMPT_VERSION,
    ThinkContextSummarizeExecutor,
    _compact_with_sediment,
    build_compact_summary,
    render_compact_summary,
    summarize_prompt_version,
)


class _RuntimeCarrier(dict):
    """Dict + attribute proxy — the kernel runtime carrier shape."""

    def __getattr__(self, name: str) -> object:
        return self.get(name)


def _ctx(state: AgentState) -> NodeContext:
    return NodeContext(runtime=_RuntimeCarrier(state=state), budget={}, metadata={})


def _budget(*, max_tokens: int | None = 100, used_tokens: int = 0) -> Budget:
    return Budget(
        max_steps=10,
        used_steps=0,
        max_tokens=max_tokens,
        used_tokens=used_tokens,
        max_cost_usd=None,
        used_cost_usd=0.0,
        max_wall_clock_seconds=None,
        started_at=utc_now(),
    )


def _state_with(budget: Budget, payload: tuple[Any, ...] = ()) -> AgentState:
    state = AgentState(trace_id="t-summarize", task="", budget=budget)
    state.retrieved_context = payload
    return state


def _over_gate_budget() -> Budget:
    return _budget(max_tokens=100, used_tokens=80)


class _FakeMemory:
    """Duck-typed stand-in for AssistantMemory (upsert only)."""

    def __init__(self) -> None:
        self.records: list[Any] = []

    def upsert(self, record: Any) -> Any:
        self.records.append(record)
        return record


class _RaisingWriter:
    def write(self, candidates: tuple[SedimentCandidate, ...]) -> int:
        raise RuntimeError("boom")


class _ZeroWriter:
    def write(self, candidates: tuple[SedimentCandidate, ...]) -> int:
        return 0


def _big_payload() -> tuple[str, ...]:
    """Payload whose head must be compacted away past the 0.7 gate."""
    return (
        "Decision: use postgres for the queue",
        "plain old log line one",
        "Commitment: ship the migration by Friday",
        "plain old log line two",
        "tail-one",
        "tail-two",
    )


def test_summarize_below_gate_emits_noop() -> None:
    receipt, new_payload, summary = _compact_with_sediment(
        payload=_big_payload(),
        budget=_budget(max_tokens=1000, used_tokens=100),
    )
    assert receipt.strategy == "noop"
    assert receipt.compacted is False
    assert summary is None
    assert new_payload == _big_payload()


def test_summarize_writer_raises_never_summarizes() -> None:
    """T1: sediment raises ⇒ no summarize; degrade honestly labeled."""
    with sediment_writer_scope(_RaisingWriter()):
        receipt, new_payload, summary = _compact_with_sediment(
            payload=_big_payload(), budget=_over_gate_budget()
        )
    assert summary is None
    assert receipt.strategy == "truncate_oldest"
    assert receipt.sedimented == 0
    assert receipt.compacted is True
    assert receipt.bytes_after < receipt.bytes_before
    assert not any("[compact-summary" in repr(item) for item in new_payload)


def test_summarize_no_writer_degrades_to_truncate_oldest() -> None:
    """T2: candidates exist but no writer installed ⇒ fail closed."""
    with sediment_writer_scope(None):
        receipt, _, summary = _compact_with_sediment(
            payload=_big_payload(), budget=_over_gate_budget()
        )
    assert summary is None
    assert receipt.strategy == "truncate_oldest"
    assert receipt.sedimented == 0
    assert receipt.bytes_after < receipt.bytes_before


def test_summarize_partial_write_degrades() -> None:
    """Writer returns 0 despite candidates ⇒ partial persistence is failure."""
    with sediment_writer_scope(_ZeroWriter()):
        receipt, _, summary = _compact_with_sediment(
            payload=_big_payload(), budget=_over_gate_budget()
        )
    assert summary is None
    assert receipt.strategy == "truncate_oldest"
    assert receipt.sedimented == 0


def test_summarize_no_candidates_proceeds_with_zero_sedimented() -> None:
    """Nothing worth sedimenting ⇒ summarize still runs (nothing to lose)."""
    noise = tuple(f"plain old log line number {i} with filler words here" for i in range(8))
    payload = (*noise, "tail-one", "tail-two")
    memory = _FakeMemory()
    with sediment_writer_scope(AssistantMemorySedimentWriter(memory)):
        receipt, new_payload, summary = _compact_with_sediment(
            payload=payload, budget=_over_gate_budget()
        )
    assert receipt.strategy == "summarize"
    assert receipt.sedimented == 0
    assert summary is not None
    assert summary.decisions == ()
    assert len(memory.records) == 0
    assert new_payload[0].startswith("[compact-summary")
    assert receipt.bytes_after <= receipt.bytes_before


def test_summarize_fixtures_full_retention_and_honest_dropped() -> None:
    """T3: planted facts 100% retained; noise lands in ``dropped``."""
    head = (
        "Decision: use postgres for the queue",
        "Decision: keep the legacy API for one quarter",
        "Commitment: ship the migration by Friday",
        "TODO: update the runbook",
        "State: queue depth is 42 and rising",
        "Open question: who owns the on-call rotation?",
        "未决事项：确认推送窗口",
        "plain noise line one with some extra filler words here",
        "another noise line two with some extra filler words here",
        "yet more noise three with some extra filler words here",
    )
    tail = ("tail-one", "tail-two")
    payload = (*head, *tail)
    memory = _FakeMemory()
    with sediment_writer_scope(AssistantMemorySedimentWriter(memory)):
        receipt, new_payload, summary = _compact_with_sediment(
            payload=payload, budget=_over_gate_budget()
        )
    assert receipt.strategy == "summarize"
    assert summary is not None
    # 100% retention of the planted facts.
    assert "use postgres for the queue" in summary.decisions
    assert "keep the legacy API for one quarter" in summary.decisions
    assert "ship the migration by Friday" in summary.commitments
    assert "update the runbook" in summary.commitments
    assert "queue depth is 42 and rising" in summary.entity_states
    assert "who owns the on-call rotation?" in summary.open_questions
    assert "确认推送窗口" in summary.open_questions
    # Noise is honestly ledgered, not silently dropped.
    dropped_text = " ".join(summary.dropped)
    assert "plain noise line one" in dropped_text
    assert "another noise line two" in dropped_text
    # Provenance on every write.
    assert len(memory.records) == 7
    for record in memory.records:
        assert record.metadata["source"] == "compaction"
        assert record.metadata["sediment_category"] in (
            "decision",
            "commitment",
            "entity_state",
            "open_question",
            "fact",
        )
    assert receipt.sedimented == 7
    # The summary block is prepended to the kept tail.
    assert new_payload[0].startswith("[compact-summary")
    assert "tail-one" in new_payload and "tail-two" in new_payload
    assert receipt.bytes_after <= receipt.bytes_before


def test_summarize_overhead_fallback_preserves_sediment_evidence() -> None:
    """Summary overhead > savings ⇒ byte cut, but sedimented count survives."""
    payload = (
        "Decision: x",
        "noise-line-aaaa",
        "noise-line-bbbb",
        "tail-one",
        "tail-two",
    )
    memory = _FakeMemory()
    with sediment_writer_scope(AssistantMemorySedimentWriter(memory)):
        receipt, new_payload, summary = _compact_with_sediment(
            payload=payload, budget=_over_gate_budget()
        )
    # Facts reached memory; the in-context summary was too expensive.
    assert len(memory.records) == 1
    assert receipt.strategy == "truncate_oldest"
    assert receipt.sedimented == 1
    assert summary is None
    assert not any("[compact-summary" in repr(item) for item in new_payload)


def test_summarize_prompt_version_matches_file() -> None:
    """T4: constant and prompt-file marker cannot drift."""
    assert summarize_prompt_version() == SUMMARIZE_PROMPT_VERSION


def test_compact_receipt_sedimented_field() -> None:
    """ADR-0283 C3: sedimented defaults to 0, settable on applied()."""
    assert CompactReceipt.noop(bytes_seen=10).sedimented == 0
    receipt = CompactReceipt.applied(
        bytes_before=100, bytes_after=50, strategy="summarize", sedimented=4
    )
    assert receipt.sedimented == 4
    assert receipt.compacted is True


def test_build_compact_summary_fact_bucket_mapping() -> None:
    """``fact``-class candidates fold into ``entity_states`` (no generic bucket)."""
    candidates = extract_sediment_candidates(("Fact: the sky is blue",))
    summary = build_compact_summary(candidates, ())
    assert isinstance(summary, CompactSummary)
    assert summary.entity_states == ("the sky is blue",)
    assert summary.prompt_version == SUMMARIZE_PROMPT_VERSION


def test_render_compact_summary_deterministic_shape() -> None:
    summary = build_compact_summary(extract_sediment_candidates(("Decision: x",)), ("noise-repr",))
    rendered = render_compact_summary(summary)
    assert rendered.startswith("[compact-summary v1]")
    assert "- x" in rendered
    assert "dropped_without_sediment: 1" in rendered
    assert render_compact_summary(summary) == rendered


def _fact_dense_payload() -> tuple[str, ...]:
    """Fact-dense head + tail: the summarize path wins the byte comparison."""
    head = (
        "Decision: use postgres for the queue",
        "Decision: keep the legacy API for one quarter",
        "Commitment: ship the migration by Friday",
        "plain noise line one with some extra filler words here",
        "another noise line two with some extra filler words here",
    )
    return (*head, "tail-one", "tail-two")


@pytest.mark.asyncio
async def test_node_execute_emits_summarize_receipt() -> None:
    """Node-level: with a writer installed, the node emits a summarize receipt."""
    memory = _FakeMemory()
    executor = ThinkContextSummarizeExecutor()
    with sediment_writer_scope(AssistantMemorySedimentWriter(memory)):
        output = await executor.node_execute(
            _ctx(_state_with(_over_gate_budget(), _fact_dense_payload())),
            NodeInput(port_values={}),
        )
    receipt: CompactReceipt = output.port_values["compact_receipt"]
    assert receipt.strategy == "summarize"
    assert receipt.sedimented == 3  # 2 decisions + 1 commitment in the head
    assert receipt.compacted is True


@pytest.mark.asyncio
async def test_node_execute_without_writer_degrades() -> None:
    """Node-level: without a writer the node fail-closes to truncate_oldest."""
    executor = ThinkContextSummarizeExecutor()
    with sediment_writer_scope(None):
        output = await executor.node_execute(
            _ctx(_state_with(_over_gate_budget(), _big_payload())),
            NodeInput(port_values={}),
        )
    receipt: CompactReceipt = output.port_values["compact_receipt"]
    assert receipt.strategy == "truncate_oldest"
    assert receipt.sedimented == 0


@pytest.mark.asyncio
async def test_node_execute_writer_failure_never_summarizes() -> None:
    """Node-level: writer failure is a handled degrade, not a graph exception."""

    class _ExplodingWriter:
        def write(self, candidates: tuple[SedimentCandidate, ...]) -> int:
            raise RuntimeError("boom")

    executor = ThinkContextSummarizeExecutor()
    with sediment_writer_scope(_ExplodingWriter()):
        output = await executor.node_execute(
            _ctx(_state_with(_over_gate_budget(), _big_payload())),
            NodeInput(port_values={}),
        )
    receipt: CompactReceipt = output.port_values["compact_receipt"]
    assert receipt.strategy == "truncate_oldest"
    assert receipt.sedimented == 0
