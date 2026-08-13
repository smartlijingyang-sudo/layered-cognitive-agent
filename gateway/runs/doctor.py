"""Run doctor — name the broken hop from jsonl + session. No HTTP."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_TERMINAL = frozenset({"completed", "failed", "canceled"})
_OPEN = frozenset({"running", "waiting_input"})
_TOOL_DONE = frozenset({"ToolInvoked", "ToolDenied"})
_RUN_FINISHED = frozenset({"AgentRunFinished", "TeamRunFinished"})


@dataclass(frozen=True, slots=True)
class HopVerdict:
    ok: bool | None
    detail: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"ok": self.ok}
        if self.detail:
            payload["detail"] = self.detail
        payload.update(self.extra)
        return payload


@dataclass(frozen=True, slots=True)
class DoctorReport:
    schema: str
    run_id: str
    trace_id: str
    status: str
    broken_hop: str | None
    summary: str
    hops: dict[str, HopVerdict]
    jsonl_path: str
    consistency: dict[str, Any]
    factory: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "run_id": self.run_id,
            "trace_id": self.trace_id,
            "status": self.status,
            "broken_hop": self.broken_hop,
            "summary": self.summary,
            "hops": {name: hop.as_dict() for name, hop in self.hops.items()},
            "jsonl_path": self.jsonl_path,
            "consistency": self.consistency,
            "factory": self.factory,
        }


@dataclass(frozen=True, slots=True)
class _JsonlScan:
    last_seq: int
    counts: dict[str, int]
    missing_plugin_state: tuple[str, ...]
    unpaired_tools: tuple[str, ...]
    has_finished: bool
    exists: bool
    rows: int


def diagnose(session: Any | None, jsonl_path: Path) -> DoctorReport:
    """Pure probe. session may be gone; jsonl still answers H2."""
    scan = _scan_jsonl(jsonl_path)
    run_id, trace_id, status, tail_seq, closed, subscribers, evicted = _session_view(
        session, jsonl_path, scan
    )

    hops: dict[str, HopVerdict] = {}
    hops["H1"] = _hop_h1(session, scan)
    hops["H2"] = _hop_h2(status, scan)
    hops["H3"] = _hop_h3(
        session,
        scan,
        status=status,
        tail_seq=tail_seq,
        closed=closed,
        subscribers=subscribers,
        evicted=evicted,
    )
    hops["H4"] = HopVerdict(ok=None, detail="server cannot see browser")
    hops["H5"] = HopVerdict(ok=None, detail="server cannot see UI")

    missing_state = list(scan.missing_plugin_state)
    factory = {"ok": not missing_state, "tools_missing_plugin_state": missing_state}
    broken = next((name for name, hop in hops.items() if hop.ok is False), None)
    summary = _summary(broken, hops, factory, scan, tail_seq, evicted)
    jsonl_eq = scan.last_seq == tail_seq if session is not None else None
    return DoctorReport(
        schema="doctor.v1",
        run_id=run_id,
        trace_id=trace_id,
        status=status,
        broken_hop=broken,
        summary=summary,
        hops=hops,
        jsonl_path=str(jsonl_path),
        consistency={"jsonl_seq_eq_tail_seq": jsonl_eq},
        factory=factory,
    )


def _session_view(
    session: Any | None, jsonl_path: Path, scan: _JsonlScan
) -> tuple[str, str, str, int, bool, int, int]:
    if session is None:
        run_id = jsonl_path.stem
        return run_id, "", "unknown", 0, True, 0, 0
    tail = getattr(session, "tail", None)
    return (
        str(getattr(session, "run_id", jsonl_path.stem)),
        str(getattr(session, "trace_id", "")),
        _status_value(session),
        int(getattr(tail, "last_seq", 0) or 0) if tail is not None else 0,
        bool(getattr(tail, "is_closed", True)) if tail is not None else True,
        int(getattr(tail, "subscriber_count", 0) or 0) if tail is not None else 0,
        int(getattr(tail, "evicted", 0) or 0) if tail is not None else 0,
    )


def _status_value(session: Any) -> str:
    status = getattr(session, "status", "")
    value = getattr(status, "value", status)
    return str(value or "")


def _hop_h1(session: Any | None, scan: _JsonlScan) -> HopVerdict:
    if session is not None or scan.exists:
        return HopVerdict(ok=True, detail="accepted")
    return HopVerdict(ok=False, detail="no session and no jsonl")


def _hop_h2(status: str, scan: _JsonlScan) -> HopVerdict:
    extra = {"last_seq": scan.last_seq, "counts": scan.counts}
    if not scan.exists or scan.rows == 0:
        return HopVerdict(ok=False, detail="jsonl empty or missing", extra=extra)
    if status in _TERMINAL and not scan.has_finished:
        return HopVerdict(ok=False, detail="terminal status without run finished", extra=extra)
    if status in _TERMINAL and scan.unpaired_tools:
        return HopVerdict(
            ok=False,
            detail="tool started without invoked/denied",
            extra={**extra, "unpaired_tools": list(scan.unpaired_tools)},
        )
    return HopVerdict(ok=True, detail="journal written", extra=extra)


def _hop_h3(
    session: Any | None,
    scan: _JsonlScan,
    *,
    status: str,
    tail_seq: int,
    closed: bool,
    subscribers: int,
    evicted: int,
) -> HopVerdict:
    extra = {
        "last_seq": tail_seq,
        "closed": closed,
        "subscribers": subscribers,
        "evicted": evicted,
    }
    if session is None:
        return HopVerdict(ok=None, detail="no live session", extra=extra)
    if evicted > 0:
        return HopVerdict(ok=False, detail="subscriber evicted", extra=extra)
    if closed and status in _OPEN:
        return HopVerdict(ok=False, detail="tail closed while run still open", extra=extra)
    if closed and scan.last_seq > tail_seq:
        return HopVerdict(ok=False, detail="tail closed behind jsonl", extra=extra)
    return HopVerdict(ok=True, detail="live tail tracking journal", extra=extra)


def _summary(
    broken: str | None,
    hops: dict[str, HopVerdict],
    factory: dict[str, Any],
    scan: _JsonlScan,
    tail_seq: int,
    evicted: int,
) -> str:
    if broken == "H3":
        hop = hops["H3"]
        return (
            f"jsonl last_seq={scan.last_seq} but live "
            f"{'closed' if hop.extra.get('closed') else 'open'} at {tail_seq}; "
            f"evicted={evicted}"
        )
    if broken == "H2":
        return hops["H2"].detail or "journal write failed"
    if broken == "H1":
        return hops["H1"].detail or "run not accepted"
    if not factory["ok"]:
        missing = ",".join(factory["tools_missing_plugin_state"])
        return f"factory missing plugin_state: {missing}"
    return "ok"


def _scan_jsonl(path: Path) -> _JsonlScan:
    if not path.is_file():
        return _JsonlScan(0, {}, (), (), False, False, 0)
    counts: Counter[str] = Counter()
    last_seq = 0
    missing: list[str] = []
    started: list[tuple[str, str]] = []
    finished: set[str] = set()
    rows = 0
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        try:
            record = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        rows += 1
        event_type = str(record.get("event_type") or "")
        counts[event_type] += 1
        seq_raw = record.get("seq") or 0
        if isinstance(seq_raw, (int, float)) or (isinstance(seq_raw, str) and seq_raw.isdigit()):
            last_seq = max(last_seq, int(seq_raw))
        raw_event = record.get("event")
        event: dict[str, Any] = raw_event if isinstance(raw_event, dict) else {}
        if event_type == "ToolStarted":
            name = str(event.get("tool_name") or "")
            invocation = str(event.get("invocation_id") or name)
            started.append((invocation, name))
            state = event.get("plugin_state")
            if not isinstance(state, dict) or not state:
                missing.append(name or invocation)
        if event_type in _TOOL_DONE:
            invocation = str(event.get("invocation_id") or event.get("tool_name") or "")
            if invocation:
                finished.add(invocation)
    unpaired = tuple(name for invocation, name in started if invocation not in finished)
    return _JsonlScan(
        last_seq=last_seq,
        counts=dict(counts),
        missing_plugin_state=tuple(missing),
        unpaired_tools=unpaired,
        has_finished=bool(_RUN_FINISHED & set(counts)),
        exists=True,
        rows=rows,
    )
