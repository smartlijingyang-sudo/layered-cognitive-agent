"""Doctor hop evaluation for the legacy RunSession execution path."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lca.plugins.transport.webserver.handlers.runs.doctor.journal import scan_jsonl
from lca.plugins.transport.webserver.handlers.runs.doctor.models import (
    OPEN_STATUSES,
    TERMINAL_STATUSES,
    DoctorReport,
    HopVerdict,
    JsonlScan,
)


def diagnose_legacy(session: Any | None, jsonl_path: Path) -> DoctorReport:
    """Build doctor.v3 from a legacy live session and its append-only JSONL journal.

    ADR-0164 Phase 4: schema 升级到 doctor.v3。 仍接受 legacy 路径(.jsonl),
    但报告 shape 跟 step-tree 一致(jsonl_path → journal_path, mode 默认 backend)。
    不产生 H8(legacy 无 step-tree 概念)。
    """
    scan = scan_jsonl(jsonl_path)
    run_id, trace_id, status, tail_seq, closed, subscribers, evicted = session_view(
        session,
        jsonl_path,
    )

    hops: dict[str, HopVerdict] = {
        "H1": hop_h1(session, scan),
        "H2": hop_h2(status, scan),
        "H3": hop_h3(
            session,
            scan,
            status=status,
            tail_seq=tail_seq,
            closed=closed,
            subscribers=subscribers,
            evicted=evicted,
        ),
        "H4": HopVerdict(ok=None, detail="mode=legacy (H4 not applicable)"),
        "H5": HopVerdict(ok=None, detail="mode=legacy (H5 not applicable)"),
        "H6": hop_h6(scan),
        "H7": hop_h7(scan),
    }
    missing_state = list(scan.missing_plugin_state)
    factory = {"ok": not missing_state, "tools_missing_plugin_state": missing_state}
    broken = next((name for name, hop in hops.items() if hop.ok is False), None)
    return DoctorReport(
        schema="doctor.v3",
        run_id=run_id,
        trace_id=trace_id,
        status=status,
        broken_hop=broken,
        summary=summary(broken, hops, factory, scan, tail_seq, evicted),
        mode="backend",
        hops=hops,
        journal_path=str(jsonl_path),
        consistency={
            "jsonl_seq_eq_tail_seq": scan.last_seq == tail_seq if session is not None else None
        },
        factory=factory,
    )


def session_view(
    session: Any | None, jsonl_path: Path
) -> tuple[str, str, str, int, bool, int, int]:
    """Project the legacy live-tail fields needed by the H1–H3 checks."""
    if session is None:
        return jsonl_path.stem, "", "unknown", 0, True, 0, 0
    tail = getattr(session, "tail", None)
    return (
        str(getattr(session, "run_id", jsonl_path.stem)),
        str(getattr(session, "trace_id", "")),
        status_value(session),
        int(getattr(tail, "last_seq", 0) or 0) if tail is not None else 0,
        bool(getattr(tail, "is_closed", True)) if tail is not None else True,
        int(getattr(tail, "subscriber_count", 0) or 0) if tail is not None else 0,
        int(getattr(tail, "evicted", 0) or 0) if tail is not None else 0,
    )


def status_value(session: Any) -> str:
    """Normalize enum-like and raw legacy status values."""
    status = getattr(session, "status", "")
    value = getattr(status, "value", status)
    return str(value or "")


def hop_h1(session: Any | None, scan: JsonlScan) -> HopVerdict:
    """Check that either a live session or persisted journal exists."""
    if session is not None or scan.exists:
        return HopVerdict(ok=True, detail="accepted")
    return HopVerdict(ok=False, detail="no session and no jsonl")


def hop_h2(status: str, scan: JsonlScan) -> HopVerdict:
    """Check journal completeness and agreement with the legacy terminal state."""
    extra = {"last_seq": scan.last_seq, "counts": scan.counts}
    if not scan.exists or scan.rows == 0:
        return HopVerdict(ok=False, detail="jsonl empty or missing", extra=extra)
    if status in TERMINAL_STATUSES and not scan.has_finished:
        return HopVerdict(ok=False, detail="terminal status without run finished", extra=extra)
    if status in TERMINAL_STATUSES and scan.journal_status and scan.journal_status != status:
        return HopVerdict(
            ok=False,
            detail="session status disagrees with journal",
            extra={**extra, "journal_status": scan.journal_status, "session_status": status},
        )
    if status in TERMINAL_STATUSES and scan.unpaired_tools:
        return HopVerdict(
            ok=False,
            detail="tool started without invoked/denied",
            extra={**extra, "unpaired_tools": list(scan.unpaired_tools)},
        )
    return HopVerdict(ok=True, detail="journal written", extra=extra)


def hop_h3(
    session: Any | None,
    scan: JsonlScan,
    *,
    status: str,
    tail_seq: int,
    closed: bool,
    subscribers: int,
    evicted: int,
) -> HopVerdict:
    """Check the legacy in-memory tail's relationship to the persisted journal."""
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
    if closed and status in OPEN_STATUSES:
        return HopVerdict(ok=False, detail="tail closed while run still open", extra=extra)
    if closed and scan.last_seq > tail_seq:
        return HopVerdict(ok=False, detail="tail closed behind jsonl", extra=extra)
    return HopVerdict(ok=True, detail="live tail tracking journal", extra=extra)


def hop_h6(scan: JsonlScan) -> HopVerdict:
    """Check whether a completed legacy run produced an observable result."""
    extra: dict[str, Any] = {
        "output_text_len": len(scan.output_text),
        "error": scan.finished_error or "",
    }
    if not scan.exists or scan.rows == 0:
        return HopVerdict(ok=None, detail="no journal data", extra=extra)
    if not scan.has_finished:
        return HopVerdict(ok=None, detail="no finish event yet", extra=extra)
    if scan.output_text_explicit and not scan.output_text.strip():
        detail = "AgentRunFinished.output_text 为空（零交付）"
        if scan.has_attachment:
            return HopVerdict(ok=False, detail=f"{detail}；有附件输入但无对应产出", extra=extra)
        return HopVerdict(ok=False, detail=detail, extra=extra)
    if scan.finished_error and scan.journal_status == "completed":
        return HopVerdict(
            ok=False,
            detail=f"completed 但有错误: {scan.finished_error[:120]}",
            extra=extra,
        )
    if scan.output_text.strip():
        return HopVerdict(ok=True, detail="有输出", extra=extra)
    return HopVerdict(ok=None, detail="output_text not present", extra=extra)


def hop_h7(scan: JsonlScan) -> HopVerdict:
    """Check legacy tool effectiveness from terminal tool facts."""
    extra: dict[str, Any] = {
        "tool_total": scan.tool_total,
        "tool_success": scan.tool_success,
        "max_consecutive_fail": scan.max_consecutive_fail,
    }
    if scan.tool_total == 0:
        return HopVerdict(ok=None, detail="no tool calls", extra=extra)
    rate = scan.tool_success / scan.tool_total
    extra["success_rate"] = round(rate, 3)
    if scan.max_consecutive_fail >= 3:
        return HopVerdict(ok=False, detail=f"连续失败 {scan.max_consecutive_fail} 次", extra=extra)
    if rate < 0.5:
        return HopVerdict(ok=False, detail=f"工具成功率 {rate:.0%}", extra=extra)
    return HopVerdict(ok=True, detail=f"成功率 {rate:.0%}", extra=extra)


def summary(
    broken: str | None,
    hops: dict[str, HopVerdict],
    factory: dict[str, Any],
    scan: JsonlScan,
    tail_seq: int,
    evicted: int,
) -> str:
    """Render the highest-priority failed hop as a compact operator summary."""
    if broken == "H3":
        hop = hops["H3"]
        return (
            f"jsonl last_seq={scan.last_seq} but live "
            f"{'closed' if hop.extra.get('closed') else 'open'} at {tail_seq}; "
            f"evicted={evicted}"
        )
    if broken in {"H1", "H2", "H6", "H7"}:
        return hops[broken].detail or "run diagnostic failed"
    if not factory["ok"]:
        missing = ",".join(factory["tools_missing_plugin_state"])
        return f"factory missing plugin_state: {missing}"
    return "ok"


__all__ = ["diagnose_legacy"]
