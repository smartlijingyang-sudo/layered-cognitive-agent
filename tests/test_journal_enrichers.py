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
from lca.layer0_infra.observability.journal.event_enrichers import (
    CausationEnricher,
    DocumentEnricher,
    EnrichmentContext,
    EnrichmentPipeline,
    PhaseLiftingEnricher,
    RedactionMarkerEnricher,
    TimestampEnricher,
    default_enrichers,
)
from lca.layer0_infra.observability.journal.jsonl_projector import (
    JsonlJournalProjector,
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


def test_projector_writes_chinese_doc_and_narrative(tmp_path: Path) -> None:
    """集成:projector 跑一遍,看 jsonl 有 _doc + 时间字段,sidecar 有叙事。"""
    path = tmp_path / "j.jsonl"
    projector = JsonlJournalProjector(path)
    projector.on_event(_stamped(1, DecisionMade(step=1, action_type="respond", response_text="hi")))
    projector.on_event(_stamped(2, StepTextDelta(step=1, text_delta="你", seq=0, channel="answer")))
    projector.on_event(_stamped(3, StepTextDelta(step=1, text_delta="好", seq=1, channel="answer")))
    projector.close()

    text = path.read_text(encoding="utf-8")
    assert "_doc" in text
    assert "occurred_at_iso" in text

    narrative = path.with_name(path.name + ".narrative.md")
    assert narrative.exists()
    md = narrative.read_text(encoding="utf-8")
    assert "DecisionMade" in md
    assert "StepTextDelta" in md
    assert "事件类型分布" in md


def test_projector_coalesces_interleaved_deltas(tmp_path: Path) -> None:
    path = tmp_path / "j.jsonl"
    projector = JsonlJournalProjector(path)
    projector.on_event(
        _stamped(1, StepTextDelta(step=1, text_delta="哈", seq=0, channel="decision"))
    )
    projector.on_event(_stamped(2, StepTextDelta(step=1, text_delta="哈", seq=1, channel="answer")))
    projector.on_event(
        _stamped(3, StepTextDelta(step=1, text_delta="好", seq=2, channel="decision"))
    )
    projector.on_event(_stamped(4, StepTextDelta(step=1, text_delta="好", seq=3, channel="answer")))
    projector.close()
    text = path.read_text(encoding="utf-8")
    # decision 通道两条合并:"哈" + "好" = "哈好";answer 通道同理
    assert '"text_delta": "哈好"' in text


def test_custom_enricher_chain_is_honoured(tmp_path: Path) -> None:
    """传入自定义 enrichers 时,默认 enricher 不再附加。"""

    @dataclass
    class TagEnricher:
        name = "tag"

        def enrich(self, record, ctx):
            out = dict(record)
            out["custom_tag"] = "ok"
            return out

    path = tmp_path / "j.jsonl"
    projector = JsonlJournalProjector(path, enrichers=(TagEnricher(),), sidecars=())
    projector.on_event(_stamped(1, DecisionMade(step=1, action_type="respond")))
    projector.close()
    text = path.read_text(encoding="utf-8")
    assert '"custom_tag": "ok"' in text
    # 默认 enricher 不再注入 _doc
    assert '"_doc"' not in text
