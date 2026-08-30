"""MemoryPolicy + CompactionPolicy + journal event wiring (PR7.D.6 / PR7.D.7).

v3 §5.5 splits memory updates into a two-phase pipeline:
- ``MemoryPolicy.commit(writes) -> MemoryCommitResult`` — authority-based
  accept / reject (e.g. low-confidence ``model_inference`` rejected).
- ``CompactionPolicy.compact(records, budget) -> tuple`` — trim the
  memory view by recency before it reaches the next perceive.

``SimpleMemorySystem`` is updated to:
- hold an injectable ``MemoryPolicy`` + ``CompactionPolicy``,
- emit ``MemoryCommitted`` once per accepted write batch,
- emit ``ContextCompacted`` from ``_shadow_compact`` at the end of
  ``perceive``.
"""

from __future__ import annotations

from lca.contracts.atoms.enums import MemoryLayer
from lca.contracts.atoms.ids import new_id
from lca.contracts.models.core.decision import Observation, Reflection
from lca.contracts.models.core.memory import MemoryRecord, MemoryTrust
from lca.contracts.models.core.state import AgentState, Budget
from lca.contracts.models.observability.journal import (
    ContextCompacted,
    MemoryCommitted,
)
from lca.layer1_cognitive.memory import SimpleMemorySystem
from lca.layer1_cognitive.memory.policy import (
    CompactionPolicy,
    MemoryAuthority,
    MemoryCommitResult,
    MemoryPolicy,
    MemoryWrite,
    MemoryWriteRejected,
    SimpleCompactionPolicy,
    SimpleMemoryPolicy,
)
from lca.layer1_cognitive.memory.semantic_compaction import SemanticCompactionPolicy


def _agent_state() -> AgentState:
    return AgentState(
        trace_id="trace-1",
        task="x",
        budget=Budget(max_steps=10),
    )


def _observation(success: bool = True) -> Observation:
    return Observation(observation_id="obs-1", success=success, payload=None)


def _reflection() -> Reflection:
    return Reflection(reflection_id="ref-1", verdict="ok")


def _write(
    *,
    authority: MemoryAuthority = MemoryAuthority.MODEL_INFERENCE,
    confidence: float = 0.8,
    content: str = "x",
    layer: MemoryLayer = MemoryLayer.WORKING,
    record_id: str | None = None,
) -> MemoryWrite:
    return MemoryWrite(
        record_id=record_id or new_id("mem"),
        layer=layer,
        authority=authority,
        content=content,
        confidence=confidence,
        source_event_refs=("obs-1",),
    )


class TestSimpleMemoryPolicy:
    def test_user_confirmed_writes_accepted(self) -> None:
        policy = SimpleMemoryPolicy()
        result = policy.commit((_write(authority=MemoryAuthority.USER_CONFIRMED),))
        assert isinstance(result, MemoryCommitResult)
        assert len(result.accepted) == 1
        assert not result.rejected

    def test_tool_observation_writes_accepted(self) -> None:
        policy = SimpleMemoryPolicy()
        result = policy.commit((_write(authority=MemoryAuthority.TOOL_OBSERVATION),))
        assert len(result.accepted) == 1

    def test_system_writes_accepted(self) -> None:
        policy = SimpleMemoryPolicy()
        result = policy.commit((_write(authority=MemoryAuthority.SYSTEM),))
        assert len(result.accepted) == 1

    def test_model_inference_below_threshold_rejected(self) -> None:
        policy = SimpleMemoryPolicy(min_confidence=0.7)
        rejected = _write(authority=MemoryAuthority.MODEL_INFERENCE, confidence=0.3)
        result = policy.commit((rejected,))
        assert not result.accepted
        assert len(result.rejected) == 1
        entry = result.rejected[0]
        assert isinstance(entry, MemoryWriteRejected)
        assert entry.write is rejected
        assert "confidence" in entry.reason.lower()

    def test_model_inference_above_threshold_accepted(self) -> None:
        policy = SimpleMemoryPolicy(min_confidence=0.5)
        accepted = _write(authority=MemoryAuthority.MODEL_INFERENCE, confidence=0.9)
        result = policy.commit((accepted,))
        assert len(result.accepted) == 1

    def test_mixed_batch(self) -> None:
        policy = SimpleMemoryPolicy(min_confidence=0.5)
        writes = (
            _write(authority=MemoryAuthority.USER_CONFIRMED),
            _write(authority=MemoryAuthority.MODEL_INFERENCE, confidence=0.1),
            _write(authority=MemoryAuthority.MODEL_INFERENCE, confidence=0.9),
            _write(authority=MemoryAuthority.TOOL_OBSERVATION),
        )
        result = policy.commit(writes)
        assert len(result.accepted) == 3
        assert len(result.rejected) == 1

    def test_commit_returns_commit_result(self) -> None:
        """``MemoryPolicy.commit`` always returns a ``MemoryCommitResult``."""
        policy = SimpleMemoryPolicy()
        result = policy.commit((_write(),))
        assert isinstance(result, MemoryCommitResult)


class TestSimpleCompactionPolicy:
    def test_compact_truncates_by_recency(self) -> None:
        from lca.contracts.models.core.memory import MemoryRecord

        records = tuple(
            MemoryRecord(
                record_id=f"r{i}",
                content=f"item-{i}",
                memory_type=MemoryLayer.WORKING,
                importance=0.5,
                recency_score=float(i),
            )
            for i in range(5)
        )
        policy = SimpleCompactionPolicy()
        kept = policy.compact(records, budget=2)
        # Highest recency_score wins → r3, r4 (i.e. last 2 items).
        assert len(kept) == 2
        assert kept[-1].record_id == "r4"
        assert kept[-2].record_id == "r3"

    def test_compact_returns_all_when_under_budget(self) -> None:
        from lca.contracts.models.core.memory import MemoryRecord

        records = tuple(
            MemoryRecord(
                record_id=f"r{i}",
                content=f"item-{i}",
                memory_type=MemoryLayer.WORKING,
                importance=0.5,
                recency_score=float(i),
            )
            for i in range(3)
        )
        policy = SimpleCompactionPolicy()
        kept = policy.compact(records, budget=10)
        assert len(kept) == 3

    def test_compact_handles_missing_recency(self) -> None:
        from lca.contracts.models.core.memory import MemoryRecord

        records = (
            MemoryRecord(
                record_id="a",
                content="x",
                memory_type=MemoryLayer.WORKING,
                importance=0.5,
                recency_score=None,
            ),
            MemoryRecord(
                record_id="b",
                content="y",
                memory_type=MemoryLayer.WORKING,
                importance=0.5,
                recency_score=0.0,
            ),
            MemoryRecord(
                record_id="c",
                content="z",
                memory_type=MemoryLayer.WORKING,
                importance=0.5,
                recency_score=1.0,
            ),
        )
        policy = SimpleCompactionPolicy()
        kept = policy.compact(records, budget=1)
        assert len(kept) == 1
        assert kept[0].record_id == "c"


class TestSemanticCompactionPolicy:
    @staticmethod
    def _records(*, count: int = 5, anchored: bool = False) -> tuple[MemoryRecord, ...]:
        return tuple(
            MemoryRecord(
                record_id=f"r{i}",
                content=f"historical evidence {i}: " + ("detail " * 90),
                memory_type=MemoryLayer.EPISODIC,
                importance=0.5,
                recency_score=float(i),
                metadata={"compaction_anchor": True} if anchored and i == 0 else {},
            )
            for i in range(count)
        )

    def test_shadow_keeps_exact_selection_and_records_candidate_provenance(self) -> None:
        records = self._records()
        policy = SemanticCompactionPolicy(mode="shadow")

        result = policy.compact(records, budget=2)

        assert tuple(record.record_id for record in result) == ("r3", "r4")
        report = policy.report(records, budget=2)
        assert report.applied is False
        assert report.reason == "shadow_candidate"
        assert report.source_record_ids == ("r0", "r1", "r2")
        assert report.summary_record_id is not None
        assert report.summary_record_id.startswith("context-summary-")
        assert report.coverage_ratio == 1.0

    def test_enforce_replaces_exactly_the_records_described_by_summary(self) -> None:
        records = self._records()
        policy = SemanticCompactionPolicy(mode="enforce", max_summary_characters=320)

        result = policy.compact(records, budget=3)

        assert len(result) == 3
        summary, *exact_records = result
        assert summary.metadata["compaction"] is True
        assert summary.metadata["source_record_ids"] == ("r0", "r1", "r2")
        assert summary.trust is MemoryTrust.UNTRUSTED_HISTORY
        assert tuple(record.record_id for record in exact_records) == ("r3", "r4")
        report = policy.report(records, budget=3)
        assert report.applied is True
        assert report.source_record_ids == tuple(summary.metadata["source_record_ids"])
        assert report.summary_record_id == summary.record_id
        assert report.result_count == 3
        assert report.compression_ratio > 0

    def test_enforce_never_removes_anchored_records(self) -> None:
        records = self._records(anchored=True)
        policy = SemanticCompactionPolicy(mode="enforce", max_summary_characters=320)

        result = policy.compact(records, budget=2)

        assert result[0].record_id == "r0"
        assert result[0].metadata["compaction_anchor"] is True
        assert result[1].metadata["source_record_ids"] == ("r1", "r2", "r3", "r4")

    def test_anchor_overflow_fails_closed_without_dropping_context(self) -> None:
        records = tuple(
            MemoryRecord(
                record_id=f"anchor-{i}",
                content="protected constraint",
                memory_type=MemoryLayer.EPISODIC,
                importance=0.5,
                metadata={"compaction_anchor": True},
            )
            for i in range(3)
        )
        policy = SemanticCompactionPolicy(mode="enforce")

        result = policy.compact(records, budget=2)

        assert result == records
        report = policy.report(records, budget=2)
        assert report.reason == "anchors_exceed_budget"


class TestProtocols:
    def test_memory_policy_is_a_protocol(self) -> None:
        from typing import Protocol

        # The Protocol annotation is structurally enforced.
        assert issubclass(MemoryPolicy, Protocol)

    def test_compaction_policy_is_a_protocol(self) -> None:
        from typing import Protocol

        assert issubclass(CompactionPolicy, Protocol)


class TestSimpleMemorySystemCommit:
    async def test_commit_emits_memory_committed_event(self) -> None:
        """``commit`` MUST emit one ``MemoryCommitted`` per accepted write."""
        system = SimpleMemorySystem()
        seen: list[MemoryCommitted] = []

        class _RecordingPolicy(SimpleMemoryPolicy):
            def commit(self, writes):
                result = super().commit(writes)
                for record in result.accepted:
                    seen.append(
                        MemoryCommitted(
                            layer=record.memory_type.value
                            if hasattr(record.memory_type, "value")
                            else str(record.memory_type),
                            record_kind=str(record.kind.value)
                            if hasattr(record.kind, "value")
                            else str(record.kind),
                            record_id=record.record_id,
                        )
                    )
                return result

        system.policy = _RecordingPolicy()
        result = system.commit((_write(),))
        assert len(result.accepted) == 1
        assert seen and seen[0].record_id == result.accepted[0].record_id

    async def test_perceive_emits_context_compacted_event(self) -> None:
        """``perceive`` MUST emit a ``ContextCompacted`` via shadow compaction."""
        from lca.contracts.models.core.memory import MemoryRecord

        system = SimpleMemorySystem()
        # Seed enough records to exceed the default budget.
        for i in range(8):
            system._append_record(
                MemoryLayer.WORKING,
                MemoryRecord(
                    record_id=f"r{i}",
                    content=f"item-{i}",
                    memory_type=MemoryLayer.WORKING,
                    importance=0.5,
                    recency_score=float(i),
                ),
            )
        seen: list[ContextCompacted] = []

        class _RecordingCompaction(SimpleCompactionPolicy):
            def __init__(self) -> None:
                super().__init__()
                self.budget = 3

            def compact(self, records, budget):
                result = super().compact(records, budget)
                seen.append(
                    ContextCompacted(
                        step=0,
                        original_kinds=tuple(
                            {r.kind.value for r in records if hasattr(r.kind, "value")}
                        ),
                        kept_kinds=tuple(
                            {r.kind.value for r in result if hasattr(r.kind, "value")}
                        ),
                    )
                )
                return result

        system.compaction = _RecordingCompaction()
        state = _agent_state()
        await system.perceive(state)
        assert seen, "perceive should invoke compaction and emit ContextCompacted"

    async def test_memory_committed_event_emitted_for_accepted_writes(self) -> None:
        """Direct test: MemoryCommitted is appended to the journal."""
        from lca.contracts.models.observability.journal import RunScope
        from lca.infrastructure.observability import bind_backends, run_scope
        from tests.support.observability_helpers import make_test_bound

        hub = make_test_bound()
        system = SimpleMemorySystem()
        with bind_backends(hub), run_scope(RunScope(trace_id="t1", run_id="r1")):
            result = system.commit((_write(),))
        # ``commit`` records MemoryCommitted events onto the ambient RunStore.
        committed_events = [
            stamped.event
            for stamped in hub.journal.store.events
            if isinstance(stamped.event, MemoryCommitted)
        ]
        assert committed_events
        # Sanity: at least one record_id matches the accepted record.
        assert any(
            ev.record_id == rec.record_id for ev in committed_events for rec in result.accepted
        )

    async def test_semantic_compaction_event_exposes_metrics_without_summary_content(self) -> None:
        from lca.contracts.models.observability.journal import RunScope
        from lca.infrastructure.observability import bind_backends, run_scope
        from tests.support.observability_helpers import make_test_bound

        class _AllWorkingRetrieval:
            def retrieve(self, layers, budget):
                del budget
                return list(layers[MemoryLayer.WORKING])

        hub = make_test_bound()
        system = SimpleMemorySystem(
            compaction=SemanticCompactionPolicy(mode="enforce", max_summary_characters=320),
            retrieval=_AllWorkingRetrieval(),
        )
        for i in range(21):
            system._append_record(
                MemoryLayer.WORKING,
                MemoryRecord(
                    record_id=f"r{i}",
                    content=f"historical tool-free context {i}: " + ("detail " * 90),
                    memory_type=MemoryLayer.WORKING,
                    importance=0.5,
                    recency_score=float(i),
                ),
            )

        with bind_backends(hub), run_scope(RunScope(trace_id="t1", run_id="r1")):
            await system.perceive(_agent_state())

        event = next(
            stamped.event
            for stamped in hub.journal.store.events
            if isinstance(stamped.event, ContextCompacted)
        )
        assert event.mode == "enforce"
        assert event.applied is True
        assert event.source_record_count == 2
        assert event.summary_record_id.startswith("context-summary-")
        assert event.original_characters > event.result_characters
        assert not hasattr(event, "summary_content")

    async def test_context_compacted_event_emitted_on_perceive(self) -> None:
        """Direct test: ContextCompacted is appended on perceive."""
        from lca.contracts.models.core.memory import MemoryRecord
        from lca.contracts.models.observability.journal import RunScope
        from lca.infrastructure.observability import bind_backends, run_scope
        from tests.support.observability_helpers import make_test_bound

        hub = make_test_bound()
        system = SimpleMemorySystem()
        for i in range(6):
            system._append_record(
                MemoryLayer.WORKING,
                MemoryRecord(
                    record_id=f"r{i}",
                    content=f"item-{i}",
                    memory_type=MemoryLayer.WORKING,
                    importance=0.5,
                    recency_score=float(i),
                ),
            )
        with bind_backends(hub), run_scope(RunScope(trace_id="t1", run_id="r1")):
            state = _agent_state()
            await system.perceive(state)
        compacted = [
            stamped.event
            for stamped in hub.journal.store.events
            if isinstance(stamped.event, ContextCompacted)
        ]
        assert compacted, "perceive must emit ContextCompacted"
