"""Coding Agent Tools 实现 helper(ADR-0065 §六 / PR-8)。

读取事件的统一辅助;**不写账本**(check_no_journal_write_in_coding_agent AST 扫描兜底)。

ADR-2026-09-02-i17-stream-align §C: spine is the SSOT
(``traces/runs/<id>/<run_id>.spine.jsonl``); legacy ``journal.jsonl`` /
``lca.journal/2`` envelopes still parse but only as a replay fallback.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from lca.contracts.models.observability.journal import (
    JournalEvent,
    RunScope,
    StampedEvent,
)
from lca.infrastructure.observability.stream.trace_inspector import TraceInspector


def _load_inspector_from_jsonl(jsonl_path: Path) -> TraceInspector:
    """从 journal.jsonl 读取 StampedEvent 重建 TraceInspector。

    仅依赖公共 file IO + JSON;不涉及 ledger / backend。
    """
    events: list[StampedEvent] = []
    if not jsonl_path.exists():
        return TraceInspector(())
    with jsonl_path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                import json as _json

                payload = _json.loads(stripped)
            except ValueError:
                continue
            if not isinstance(payload, dict):
                continue
            stamped = _event_from_payload(payload)
            if stamped is not None:
                events.append(stamped)
    return TraceInspector(tuple(events))


def _event_from_payload(payload: dict[str, object]) -> StampedEvent | None:
    """journal.jsonl 行 → StampedEvent(skeleton)。

    Recognises two envelopes (ADR-2026-09-02-i17-stream-align §C):

    - **spine v3** (preferred): top-level ``execution_point`` /
      ``channel`` / ``when`` / ``payload`` / ``causality_id`` — what
      ``traces/runs/<id>/<run_id>.spine.jsonl`` writes today.
    - **legacy v2**: nested ``scope`` / ``descriptor.type`` /
      ``run_seq`` / ``data`` — what the old ``lca.journal/2`` envelope
      used. Kept for replay compatibility only.

    Returns ``None`` when neither envelope matches (e.g. a migration
    marker line), so the loader skips it without aborting the trace.
    """
    if "execution_point" in payload or "when" in payload or "payload" in payload:
        scope_raw = payload.get("scope")
        if not isinstance(scope_raw, dict):
            scope_raw = {}
        seq_value = payload.get("sequence")
        seq_field = seq_value if isinstance(seq_value, int) else 0
        when_field = payload.get("when_corrected") or payload.get("when") or 0.0
        try:
            ts_value = float(when_field)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            ts_value = 0.0
        event_type = str(payload.get("execution_point", "") or "")
        # Carry the spine top-level ``channel`` / ``outcome`` into the
        # data dict so TraceInspector failure-detection (which keys off
        # ``data["channel"]`` / ``data["outcome"]``) can recognise v3
        # events without forcing every consumer to learn the new envelope.
        inner_payload = dict(payload.get("payload", {}) or {})
        channel = payload.get("channel")
        if isinstance(channel, str) and channel:
            inner_payload.setdefault("channel", channel)
        outcome = payload.get("outcome")
        if isinstance(outcome, str) and outcome:
            inner_payload.setdefault("outcome", outcome)
        # Spine parent/child carries via span_id / parent_span_id.
        # ``parent_seq`` is unknown in spine (chain is via causality_id
        # hashing); fall back to None — see ``_causal_chain``.
        parent_seq_raw = payload.get("parent_seq")
        parent_seq_value: int | None = (
            int(parent_seq_raw) if isinstance(parent_seq_raw, int) else None
        )
        return StampedEvent(
            seq=seq_field,
            ts=ts_value,
            scope=RunScope(
                trace_id=str(scope_raw.get("trace_id", "")),
                run_id=str(scope_raw.get("run_id", "")) or str(payload.get("run_id", "") or ""),
            ),
            event=JournalEvent(),
            event_type=event_type,
            data=inner_payload,
            parent_seq=parent_seq_value,
        )

    scope_raw = payload.get("scope", {}) or {}
    if not isinstance(scope_raw, dict):
        scope_raw = {}
    descriptor = payload.get("descriptor", {}) or {}
    event_type = ""
    if isinstance(descriptor, dict):
        event_type = str(descriptor.get("type", ""))
    if not event_type:
        event_type = str(payload.get("event_type", ""))
    return StampedEvent(
        seq=int(payload.get("run_seq", payload.get("seq", 0)) or 0),
        ts=float(payload.get("occurred_at", payload.get("ts", 0.0)) or 0.0),
        scope=RunScope(
            trace_id=str(scope_raw.get("trace_id", "")),
            run_id=str(scope_raw.get("run_id", "")),
        ),
        event=JournalEvent(),
        event_type=event_type,
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
