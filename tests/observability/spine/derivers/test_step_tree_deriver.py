"""Parity test: StepTreeDeriver must produce equivalent journal.json to the legacy
StepGroupedBackend when fed the same sequence of spine events (Task 2.2).

PR-2 parallel-write phase: both legacy ``StepGroupedBackend`` and the
new ``StepTreeDeriver`` (wrapping it) are subscribed to ``EventSpine``.
Emitting the same events through both should result in identical
``journal.json`` content on disk.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from lca.contracts.models.observability import (
    JournalMetadata,
    ReflectTrace,
    StepContext,
    ThinkingTrace,
    ToolCallRecord,
    ToolResult,
)
from lca.infrastructure.observability.journal.step import read_step_document
from lca.infrastructure.observability.journal.step.backend import StepGroupedBackend
from lca.infrastructure.observability.spine.context import SpineContext
from lca.infrastructure.observability.spine.event_record import EventRecord
from lca.infrastructure.observability.spine.event_spine import EventSpine
from lca.infrastructure.observability.spine.sinks.file_sink import FileSink
from lca.runtime.step_lifecycle import (
    StepLifecycleStore,
    reset_lifecycle_store,
    set_lifecycle_store,
)


def _meta() -> JournalMetadata:
    return JournalMetadata(
        agent_role="agt_test",
        strategy_key="solo",
        plan_ref="plan_parity_001",
        objective="parity test",
    )


def _make_event(**overrides: object) -> EventRecord:
    base: dict[str, object] = {
        "execution_point": "brain.think.start",
        "channel": "fact",
        "span_id": "01HM",
        "parent_span_id": None,
        "sequence": 1,
        "epoch": 1,
        "causality_id": "sha256:abc",
        "outcome": None,
        "when": datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
        "when_corrected": datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
        "prev_event_hash": None,
        "run_id": "r1",
        "step_id": "s1",
        "payload": {"x": 1},
    }
    base.update(overrides)
    return EventRecord(**base)  # type: ignore[arg-type]


def test_step_tree_deriver_produces_equivalent_journal_json(
    tmp_path: Path,
) -> None:
    """StepTreeDeriver (wrapping StepGroupedBackend) and standalone
    StepGroupedBackend produce identical journal.json when driven by the
    same lifecycle state and event stream.
    """

    SpineContext.set_run("r-parity")
    store = StepLifecycleStore()
    store.bind_run(run_id="r-parity", trace_id="t-parity", metadata=_meta())
    token = set_lifecycle_store(store)
    try:
        journal_a = tmp_path / "legacy_journal.json"
        journal_b = tmp_path / "deriver_journal.json"
        legacy_backend = StepGroupedBackend(output_path=journal_a, lifecycle_store=store)
        from lca.infrastructure.observability.spine.derivers.step_tree import (
            StepTreeDeriver,
        )

        deriver = StepTreeDeriver(
            backend=StepGroupedBackend(output_path=journal_b, lifecycle_store=store)
        )

        from lca.runtime import step_lifecycle

        step_lifecycle.open_step("think", context=StepContext(objective="parity"))
        step_lifecycle.record_thinking(
            ThinkingTrace(
                model="qwen3.7-plus",
                latency_ms=42,
                reasoning="reasoning text",
                decision="respond",
            )
        )
        step_lifecycle.record_tool_call(
            ToolCallRecord(invocation_id="t1", name="executeCode", arguments={})
        )
        step_lifecycle.record_tool_result(ToolResult(ok=True, latency_ms=10, delta_summary="ok"))
        step_lifecycle.record_reflect(ReflectTrace(summary="done"))
        step_lifecycle.close_step("ok")
        # close_document on the store takes a doc; use the facade instead
        # which goes through store.close_document(doc, outcome=...)
        from lca.infrastructure.observability import facade as fd

        fd.step_close_document(outcome="completed")

        sink_dir = tmp_path / "sink"
        sink = FileSink(sink_dir, run_id="r-parity")
        spine = EventSpine(
            sinks=[sink],
            subscribers=[deriver.on_event, legacy_backend.write],
        )
        for seq in (1, 2, 3):
            spine.append(
                execution_point="brain.think.start",
                channel="fact",
                caller_payload={"i": seq},
            )
        spine.close()

        legacy_backend.flush()
        deriver.flush()  # type: ignore[attr-defined]

        assert journal_a.exists(), "legacy backend did not flush journal.json"
        assert journal_b.exists(), "deriver did not flush journal.json"

        doc_a = read_step_document(journal_a)
        doc_b = read_step_document(journal_b)
        assert doc_a.metadata.objective == doc_b.metadata.objective
        assert len(doc_a.steps) == len(doc_b.steps)
        assert doc_a.steps[0].thinking.reasoning == doc_b.steps[0].thinking.reasoning
        assert doc_a.steps[0].reflect.summary == doc_b.steps[0].reflect.summary

        def _scrub_timestamps(payload: object) -> object:
            if isinstance(payload, dict):
                keys = {
                    "started_at",
                    "closed_at",
                    "entered_at",
                    "exited_at",
                }
                return {k: (0.0 if k in keys else _scrub_timestamps(v)) for k, v in payload.items()}
            if isinstance(payload, list):
                return [_scrub_timestamps(v) for v in payload]
            return payload

        json_a = json.loads(journal_a.read_text())
        json_b = json.loads(journal_b.read_text())
        assert _scrub_timestamps(json_a) == _scrub_timestamps(json_b)
    finally:
        reset_lifecycle_store(token)


def test_step_tree_deriver_satisfies_deriver_protocol(tmp_path: Path) -> None:
    """Structural check: StepTreeDeriver must satisfy the Deriver Protocol."""
    from lca.infrastructure.observability.spine.derivers.base import Deriver
    from lca.infrastructure.observability.spine.derivers.step_tree import (
        StepTreeDeriver,
    )

    store = StepLifecycleStore()
    store.bind_run(run_id="r2", trace_id="t2", metadata=_meta())
    backend = StepGroupedBackend(output_path=tmp_path / "x.json", lifecycle_store=store)
    deriver = StepTreeDeriver(backend=backend)
    assert isinstance(deriver, Deriver)
    assert callable(deriver.on_event)


def test_step_tree_deriver_on_event_does_not_raise(tmp_path: Path) -> None:
    """An incoming spine event must not raise from on_event (FD-2
    containment is at the spine layer, but the deriver itself must also
    not blow up on a well-formed event)."""
    from lca.infrastructure.observability.spine.derivers.step_tree import (
        StepTreeDeriver,
    )

    store = StepLifecycleStore()
    store.bind_run(run_id="r3", trace_id="t3", metadata=_meta())
    backend = StepGroupedBackend(output_path=tmp_path / "j.json", lifecycle_store=store)
    deriver = StepTreeDeriver(backend=backend)
    deriver.on_event(_make_event())
