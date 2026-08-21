"""Coding Agent Tools 实现 helper(ADR-0065 §六 / PR-8)。

读取事件的统一辅助;**不写账本**(check_no_journal_write_in_coding_agent AST 扫描兜底)。
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from lca.contracts.models.observability.journal import StampedEvent
from lca.layer0_infra.observability.trace_inspector import TraceInspector


def _load_inspector_from_jsonl(jsonl_path: Path) -> TraceInspector:
    """从 journal.jsonl 读取 StampedEvent 重建 TraceInspector。

    仅依赖公共 file IO + JSON;不涉及 ledger / backend。
    """
    import json

    events: list[StampedEvent] = []
    if not jsonl_path.exists():
        return TraceInspector(())
    with jsonl_path.open("r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            events.append(_event_from_payload(payload))
    return TraceInspector(tuple(events))


def _event_from_payload(payload: dict[str, object]) -> StampedEvent:
    """journal.jsonl 行 → StampedEvent(skeleton)。"""
    from lca.contracts.models.observability.journal import (
        JournalEvent,
        RunScope,
    )

    scope_raw = payload.get("scope", {}) or {}
    scope = RunScope(
        trace_id=str(scope_raw.get("trace_id", "")),
        run_id=str(scope_raw.get("run_id", "")),
    )
    return StampedEvent(
        seq=int(payload.get("seq", 0)),
        ts=float(payload.get("ts", 0.0)),
        scope=scope,
        event=JournalEvent(),
        event_type=str(payload.get("event_type", "")),
        data=payload.get("data", {}) or {},
    )


def _serialize_report(report) -> dict[str, object]:
    """TraceReport / TraceReport-like → JSON-serializable dict。"""
    return {
        "trace_id": getattr(report, "trace_id", ""),
        "event_count": getattr(report, "event_count", 0),
        "summary": getattr(report, "summary", ""),
        "events": list(getattr(report, "events", ())),
        "causal_chain": list(getattr(report, "causal_chain", ())),
        "bottlenecks": list(getattr(report, "bottlenecks", ())),
        "plugin_graph": getattr(report, "plugin_graph", ""),
    }


__all__ = ["_inspector_events", "_load_inspector_from_jsonl", "_serialize_report"]


def _inspector_events(inspector: TraceInspector) -> Sequence[StampedEvent]:
    """从 TraceInspector 派生 events 序列(从 internal _events 读取)。"""
    return list(getattr(inspector, "_events", ()))
