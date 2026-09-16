"""Coding Agent Tools 实现 helper(ADR-0065 §六 / PR-8)。

读取事件的统一辅助;**不写账本**(check_no_journal_write_in_coding_agent AST 扫描兜底)。

ADR-2026-09-02-i17-stream-align §C: spine is the SSOT
(``traces/runs/<id>/<run_id>.spine.jsonl``); legacy ``journal.jsonl`` /
``lca.journal/2`` envelopes still parse but only as a replay fallback.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path

from lca.contracts.atoms.ids.ids import RunId, TraceId
from lca.contracts.models.observability.journal.journal import (
    JournalEvent,
    RunScope,
    StampedEvent,
)
from lca.infrastructure.observability.stream.trace_inspector import TraceInspector


def _object_to_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _object_to_float(value: object, default: float = 0.0) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def _to_epoch_seconds(value: object) -> float:
    """Coerce a spine ``ts`` / ``when`` field to epoch seconds.

    The spine writer emits ISO-8601 with offset; the legacy v2 envelope
    emitted a numeric ``occurred_at``. Both shapes appear in persisted
    ledgers, so both parse.
    """
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str) or not value.strip():
        return 0.0
    try:
        return float(value)
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return 0.0


def _split_spine_event_id(value: object) -> tuple[str, int | None]:
    """Split a spine ``event_id`` (``"<run_id>:<seq>"``) into its parts.

    ``event_id`` is the only place the spine v3 record carries the run id
    and the ledger sequence: there is no top-level ``run_id`` and no
    ``sequence`` field. Returns ``("", None)`` when the shape does not
    match so callers fall through to their other sources.
    """
    if not isinstance(value, str) or ":" not in value:
        return "", None
    run_id, _, seq = value.rpartition(":")
    if not run_id or not seq.isdigit():
        return "", None
    return run_id, int(seq)


def _mapping_value(value: object) -> dict[str, object]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


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
      ``channel`` / ``event_id`` / ``ts`` / ``payload`` /
      ``causation_id`` — what
      ``traces/runs/<id>/<run_id>.spine.jsonl`` writes today. ``run_id``
      and the ledger sequence live inside ``event_id``
      (``"<run_id>:<seq>"``) and ``payload``, not at top level.
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
        # ``inner_payload`` first: the spine record carries ``run_id`` /
        # ``trace_id`` inside ``payload``, not at top level.
        inner_payload = _mapping_value(payload.get("payload", {}))
        event_id_run, event_id_seq = _split_spine_event_id(payload.get("event_id"))
        seq_value = payload.get("sequence")
        seq_field = seq_value if isinstance(seq_value, int) else (event_id_seq or 0)
        when_field = payload.get("when_corrected") or payload.get("when") or payload.get("ts")
        ts_value = _to_epoch_seconds(when_field)
        event_type = str(payload.get("execution_point", "") or "")
        # Carry the spine top-level ``channel`` / ``outcome`` into the
        # data dict so TraceInspector failure-detection (which keys off
        # ``data["channel"]`` / ``data["outcome"]``) can recognise v3
        # events without forcing every consumer to learn the new envelope.
        channel = payload.get("channel")
        if isinstance(channel, str) and channel:
            inner_payload.setdefault("channel", channel)
        outcome = payload.get("outcome")
        if isinstance(outcome, str) and outcome:
            inner_payload.setdefault("outcome", outcome)
        run_id_value = (
            str(scope_raw.get("run_id", "") or "")
            or str(payload.get("run_id", "") or "")
            or str(inner_payload.get("run_id", "") or "")
            or event_id_run
        )
        trace_id_value = (
            str(scope_raw.get("trace_id", "") or "")
            or str(payload.get("trace_id", "") or "")
            or str(inner_payload.get("trace_id", "") or "")
        )
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
                trace_id=TraceId(trace_id_value),
                run_id=RunId(run_id_value),
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
        seq=_object_to_int(payload.get("run_seq", payload.get("seq", 0)) or 0),
        ts=_object_to_float(payload.get("occurred_at", payload.get("ts", 0.0)) or 0.0),
        scope=RunScope(
            trace_id=TraceId(str(scope_raw.get("trace_id", ""))),
            run_id=RunId(str(scope_raw.get("run_id", ""))),
        ),
        event=JournalEvent(),
        event_type=event_type,
        data=_mapping_value(payload.get("data", {})),
    )


def _serialize_report(report: object) -> dict[str, object]:
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
