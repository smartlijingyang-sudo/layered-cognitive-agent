"""Read-only fact extraction from legacy run and Session Spine JSONL stores."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from lca.infrastructure.observability.journal.engine.journal_io import (
    load_journal_records,
    record_normalize,
)
from lca.plugins.transport.webserver.handlers.runs.doctor.models import (
    RUN_FINISHED_EVENTS,
    TOOL_TERMINAL_EVENTS,
    JsonlScan,
)


def session_jsonl_last_seq(path: Path) -> int:
    """Return the last durable Session event sequence, or ``-1`` when unavailable."""
    if not path.is_file():
        return -1
    last_seq = -1
    for raw in path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if record.get("kind") != "event":
            continue
        seq = record.get("seq")
        if isinstance(seq, int):
            last_seq = max(last_seq, seq)
    return last_seq


def scan_jsonl(path: Path) -> JsonlScan:
    """Fold a legacy JSONL journal into the facts required by doctor.v2."""
    if not path.is_file():
        return JsonlScan(0, {}, (), (), False, "", False, 0, "", False, "", 0, 0, 0, False)
    counts: Counter[str] = Counter()
    last_seq = 0
    # ADR-0102: ``missing_plugin_state`` is no longer derivable from jsonl —
    # ``projected_state`` is SSE-only.  Kept as an empty tuple in the
    # returned ``JsonlScan`` so legacy consumers don't break.
    missing: list[str] = []
    started: list[tuple[str, str]] = []
    finished: set[str] = set()
    rows = 0
    journal_status = ""
    output_text = ""
    output_text_explicit = False
    finished_error = ""
    tool_total = 0
    tool_success = 0
    max_consecutive_fail = 0
    current_consecutive_fail = 0
    has_attachment = False
    for record in load_journal_records(path, strict=False):
        rows += 1
        normalized = record_normalize(record)
        descriptor = normalized.get("descriptor", {}) or {}
        # ADR-2026-09-02-i17-traceback §D6: doctor reads BOTH the
        # legacy ``event_type`` (SSE-shaped records) AND the journal
        # ``execution_point`` (the only field populated for
        # ``events.jsonl``). Falling back to execution_point was
        # missing in earlier revisions — every journal entry was
        # recorded as ``event_type=""`` so RUN_FINISHED_EVENTS never
        # matched. That is the H2 false-positive addressed by the
        # ADR.
        event_type = str(
            descriptor.get("type")
            or record.get("event_type")
            or record.get("execution_point")
            or ""
        )
        counts[event_type] += 1
        seq_raw = normalized.get("run_seq", record.get("seq")) or 0
        if isinstance(seq_raw, (int, float)) or (isinstance(seq_raw, str) and seq_raw.isdigit()):
            last_seq = max(last_seq, int(seq_raw))
        raw_event = normalized.get("data") or record.get("event")
        event: dict[str, Any] = raw_event if isinstance(raw_event, dict) else {}
        if event_type in RUN_FINISHED_EVENTS:
            journal_status = str(event.get("status") or "")
            if "output_text" in event:
                output_text_explicit = True
                output_text = str(event.get("output_text") or "")
            finished_error = str(event.get("error") or "")
        if event_type == "ToolStarted":
            name = str(event.get("tool_name") or "")
            invocation = str(event.get("invocation_id") or name)
            started.append((invocation, name))
            # ADR-0102: the renderer-facing projection (``projected_state``)
            # is SSE-only — jsonl never carries it (stripped by
            # ``JsonlJournalProjector._strip_sse_only_fields`` before disk
            # write).  Therefore the doctor cannot fact-check the projection
            # from jsonl; that responsibility lives in the contract /
            # ``scan_jsonl`` layer (static, profile-time) and in the SSE
            # encoder (live).  The previous ``plugin_state`` check on
            # ``ToolStarted`` was a false positive against ADR-0102's new
            # shape, so it is intentionally dropped here.
        if event_type in TOOL_TERMINAL_EVENTS:
            invocation = str(event.get("invocation_id") or event.get("tool_name") or "")
            if invocation:
                finished.add(invocation)
            if event_type == "ToolInvoked":
                tool_total += 1
                is_success = bool(event.get("ok", event.get("success", False)))
                if is_success:
                    tool_success += 1
                    current_consecutive_fail = 0
                else:
                    current_consecutive_fail += 1
                    max_consecutive_fail = max(max_consecutive_fail, current_consecutive_fail)
        if event_type == "AgentRunStarted":
            objective = str(event.get("objective") or "")
            has_attachment = "<file" in objective or "<files_info>" in objective
    unpaired = tuple(name for invocation, name in started if invocation not in finished)
    return JsonlScan(
        last_seq=last_seq,
        counts=dict(counts),
        missing_plugin_state=tuple(missing),
        unpaired_tools=unpaired,
        has_finished=bool(RUN_FINISHED_EVENTS & set(counts)),
        journal_status=journal_status,
        exists=True,
        rows=rows,
        output_text=output_text,
        output_text_explicit=output_text_explicit,
        finished_error=finished_error,
        tool_total=tool_total,
        tool_success=tool_success,
        max_consecutive_fail=max_consecutive_fail,
        has_attachment=has_attachment,
    )


__all__ = ["scan_jsonl", "session_jsonl_last_seq"]
