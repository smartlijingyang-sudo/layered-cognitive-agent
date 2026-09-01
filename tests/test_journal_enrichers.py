"""每个 enricher / sidecar 的最小行为合约。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lca.contracts.models.observability.journal import (
    DecisionMade,
    RunScope,
    StampedEvent,
    StepTextDelta,
)
from lca.infrastructure.observability.journal.enrichment.event_enrichers import (
    CausationEnricher,
    DocumentEnricher,
    EnrichmentContext,
    EnrichmentPipeline,
    PhaseLiftingEnricher,
    RedactionMarkerEnricher,
    TimestampEnricher,
    default_enrichers,
)


def _stamped(seq: int, event, *, ts: float | None = None, role: str = "solo"):
    return StampedEvent(
        seq=seq,
        ts=1.0 + seq if ts is None else ts,
        scope=RunScope(trace_id="t", run_id="r", agent_role=role, step=1),
        event=event,
        event_type=type(event).__name__,
        data={},
        event_id=f"01TEST{seq:020d}",
    )


def test_document_enricher_injects_chinese_summary() -> None:
    enricher = DocumentEnricher()
    record = {
        "descriptor": {"type": "DecisionMade"},
        "data": {"action_type": "respond"},
    }
    out = enricher.enrich(record, EnrichmentContext())
    assert "_doc" in out
    assert "决策" in out["_doc"]["summary"]


def test_timestamp_enricher_adds_iso_and_elapsed() -> None:
    enricher = TimestampEnricher()
    ctx = EnrichmentContext()
    base = {
        "descriptor": {"type": "StepTextDelta"},
        "scope": {"agent_role": "a", "step": 1, "run_id": "r"},
        "occurred_at": 1_700_000_000.0,
        "data": {"text_delta": "hi"},
    }
    ctx.note_event(base)
    second = dict(base, occurred_at=1_700_000_000.5)
    out = enricher.enrich(second, ctx)
    assert out["occurred_at_iso"].startswith("2023-")
    assert out["elapsed_ms"] == 500


def test_causation_enricher_threads_parent_event_id() -> None:
    enricher = CausationEnricher()
    ctx = EnrichmentContext()
    first = {
        "descriptor": {"type": "DecisionMade"},
        "scope": {"agent_role": "a", "step": 1, "run_id": "r"},
        "occurred_at": 1.0,
        "event_id": "e1",
        "causation": {},
    }
    ctx.note_event(first)
    second = {
        "descriptor": {"type": "AgentRunFinished"},
        "scope": {"agent_role": "a", "step": 1, "run_id": "r"},
        "occurred_at": 2.0,
        "causation": {},
    }
    out = enricher.enrich(second, ctx)
    assert out["causation"]["parent_event_id"] == "e1"
    assert out["prev_event_type"] == "DecisionMade"


def test_causation_enricher_does_not_cross_scopes() -> None:
    """不同 actor_role 的事件互不污染 parent_event_id。"""
    enricher = CausationEnricher()
    ctx = EnrichmentContext()
    ctx.note_event(
        {
            "descriptor": {"type": "DecisionMade"},
            "scope": {"agent_role": "a", "step": 1, "run_id": "r"},
            "occurred_at": 1.0,
            "event_id": "e1",
            "causation": {},
        }
    )
    out = enricher.enrich(
        {
            "descriptor": {"type": "StepTextDelta"},
            "scope": {"agent_role": "b", "step": 1, "run_id": "r"},
            "occurred_at": 2.0,
            "causation": {},
        },
        ctx,
    )
    assert "parent_event_id" not in out.get("causation", {})


def test_phase_lifting_enricher_promotes_runtime_attrs() -> None:
    enricher = PhaseLiftingEnricher()
    record = {
        "descriptor": {"type": "RuntimeObserved"},
        "data": {
            "kind": "plugin",
            "operation": "phase.fact",
            "source": "think.main",
            "attributes": {
                "actor_role": "researcher",
                "payload": {"semantic_phase": "think", "fact_id": "abc"},
            },
        },
        "scope": {"agent_role": "", "step": 0, "run_id": "r"},
    }
    out = enricher.enrich(record, EnrichmentContext())
    assert out["phase"] == "think"
    assert out["fact_id"] == "abc"
    assert out["plugin"] == "think"
    assert out["scope"]["agent_role"] == "researcher"


def test_phase_lifting_is_noop_for_non_runtime() -> None:
    enricher = PhaseLiftingEnricher()
    record = {
        "descriptor": {"type": "DecisionMade"},
        "data": {"action_type": "respond"},
    }
    out = enricher.enrich(record, EnrichmentContext())
    assert "phase" not in out


def test_redaction_marker_enricher_records_lengths() -> None:
    enricher = RedactionMarkerEnricher()
    long = "x" * 700
    record = {
        "descriptor": {"type": "LlmCallCompleted"},
        "data": {"prompt_preview": long, "model": "demo"},
    }
    out = enricher.enrich(record, EnrichmentContext())
    # 标记写到顶层 _redaction,不污染 data —— 避免破坏 dataclass 重建
    assert "_redaction" in out
    assert out["_redaction"]["prompt_preview"]["len"] == 700
    assert out["_redaction"]["prompt_preview"]["truncated"] is True
    assert "prompt_preview_len" not in out["data"]


def test_enrichment_pipeline_runs_in_order_and_recovers() -> None:
    """一个 enricher 抛异常不能影响其它 enricher;pipeline 仍产出可读 dict。"""

    @dataclass
    class Boom:
        name = "boom"

        def enrich(self, record, ctx):
            raise RuntimeError("kapow")

    pipeline = EnrichmentPipeline(
        enrichers=(DocumentEnricher(), Boom(), TimestampEnricher()),
        context=EnrichmentContext(),
    )
    out = pipeline.run(
        {
            "descriptor": {"type": "DecisionMade"},
            "scope": {"agent_role": "a", "step": 1, "run_id": "r"},
            "occurred_at": 1_700_000_000.0,
            "data": {"action_type": "respond"},
        }
    )
    assert "_doc" in out
    assert "occurred_at_iso" in out


def test_default_enrichers_contain_doc_and_causation() -> None:
    names = {e.name for e in default_enrichers()}
    assert {"doc", "timestamp", "causation", "phase_lift", "redaction_marker"} <= names


def test_enrichment_pipeline_no_longer_attached_to_step_tree(tmp_path: Path) -> None:
    """ADR-0164 Phase 7: enricher pipeline 已随 JsonlJournalProjector 删除。

    step-tree 不需要 enricher(每原语已经是结构化字段)。
    这个测试保留 enricher pipeline unit test 范畴 — 通过 EnrichmentPipeline
    直接调用验证 _doc / timestamp / causation 注入逻辑,不需要 projector。
    """
    # pipeline 直接调用 enrichment, 不需要 projector 落盘
    pipeline = EnrichmentPipeline(enrichers=default_enrichers())
    ctx = EnrichmentContext(run_id="r1", trace_id="t1")
    # 需要 descriptor.type 才能触发 DocumentEnricher / CausationEnricher
    # 需要 occurred_at (epoch float) 触发 TimestampEnricher
    record = {
        "descriptor": {"type": "AgentRunStarted"},
        "occurred_at": 1000.0,
        "data": {"objective": "测试", "objective_preview": "测试"},
        "scope": {"agent_role": "x", "step": 1},
    }
    enriched = pipeline.run(record)
    ctx.note_event(enriched)
    # _doc / occurred_at_iso 应该被注入
    assert "_doc" in enriched
    assert "occurred_at_iso" in enriched


def test_step_tree_does_not_emit_narrative_sidecar(tmp_path: Path) -> None:
    """ADR-0164: step-tree 路径不写 narrative.md(由 StepNarrativeWriter 接管)。"""
    from lca.contracts.models.observability import (
        JournalMetadata,
        empty_document,
    )
    from lca.infrastructure.observability.journal.step.projector import (
        StepGroupedProjector,
    )

    path = tmp_path / "j.json"
    meta = JournalMetadata(
        agent_role="x",
        strategy_key="solo",
        plan_ref="",
        objective="t",
    )
    doc = empty_document(run_id="r", trace_id="t", metadata=meta, started_at=0.0)
    StepGroupedProjector(path).write(doc)

    # step-tree 不应自动产出 narrative.md
    assert not (tmp_path / "j.narrative.md").exists()
    # 写 journal.json 即可
    assert path.exists()


def test_custom_enricher_pipeline_still_works_via_direct_call(tmp_path: Path) -> None:
    """自定义 enricher 通过 EnrichmentPipeline.run 直接调用测试。

    不依赖 projector(已删除)。
    """

    @dataclass
    class TagEnricher:
        name = "tag"

        def enrich(self, record, ctx):
            out = dict(record)
            out["custom_tag"] = "ok"
            return out

    pipeline = EnrichmentPipeline(enrichers=(TagEnricher(),))
    record = {"data": {}}
    enriched = pipeline.run(record)
    assert enriched["custom_tag"] == "ok"

    # 对照: 默认 enricher 链会注入 _doc / occurred_at_iso
    default_pipeline = EnrichmentPipeline(enrichers=default_enrichers())
    ctx = EnrichmentContext(run_id="r", trace_id="t")
    default_record = {
        "descriptor": {"type": "AgentRunStarted"},
        "occurred_at": 1000.0,
        "data": {"objective": "测试"},
        "scope": {"agent_role": "x", "step": 1},
    }
    default_enriched = default_pipeline.run(default_record)
    ctx.note_event(default_enriched)
    assert "_doc" in default_enriched
    assert "occurred_at_iso" in default_enriched
