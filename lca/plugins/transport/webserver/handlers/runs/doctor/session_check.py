"""Doctor.v2 projection for the durable Session Spine execution path."""

from __future__ import annotations

from lca.contracts.harness.state.projection import ProjectionSnapshot
from lca.plugins.transport.webserver.handlers.runs.doctor.models import DoctorReport, HopVerdict


def diagnose_session_projection(
    *,
    run_id: str,
    snapshot: ProjectionSnapshot,
    persisted_seq: int,
    persistence_ref: str,
) -> DoctorReport:
    """Build a doctor.v2 report from authoritative Session Spine projections."""
    activity = snapshot.values.get("activity", {})
    conversation = snapshot.values.get("conversation", {})
    status = str(activity.get("status") or "unknown") if isinstance(activity, dict) else "unknown"
    output = (
        str(conversation.get("last_assistant_message") or "")
        if isinstance(conversation, dict)
        else ""
    )
    h2_extra: dict[str, int] = {
        "projection_seq": snapshot.as_of_seq,
        "persisted_seq": persisted_seq,
    }
    if snapshot.as_of_seq < 0:
        h1 = HopVerdict(ok=False, detail="session projection missing")
        h2 = HopVerdict(ok=None, detail="not evaluated", extra=h2_extra)
        h3 = HopVerdict(ok=None, detail="not evaluated")
    else:
        h1 = HopVerdict(ok=True, detail="accepted by Session Spine")
        h2 = HopVerdict(
            ok=persisted_seq in {-1, snapshot.as_of_seq},
            detail=(
                "projection and persisted session are aligned"
                if persisted_seq in {-1, snapshot.as_of_seq}
                else "projection is ahead of persisted session"
            ),
            extra=h2_extra,
        )
        h3 = HopVerdict(ok=True, detail="durable projection available")
    h4 = HopVerdict(ok=None, detail="server cannot see browser")
    h5 = HopVerdict(ok=None, detail="server cannot see UI")
    if status == "completed":
        h6 = HopVerdict(
            ok=bool(output.strip()),
            detail="有输出" if output.strip() else "completed 但 projection 无输出",
            extra={"output_text_len": len(output)},
        )
    else:
        h6 = HopVerdict(ok=None, detail="output not applicable before completion")
    h7 = HopVerdict(ok=None, detail="tool effectiveness is not exposed by projection")
    hops = {"H1": h1, "H2": h2, "H3": h3, "H4": h4, "H5": h5, "H6": h6, "H7": h7}
    broken = next((name for name, hop in hops.items() if hop.ok is False), None)
    summary = "ok" if broken is None else hops[broken].detail or "session diagnostic failed"
    return DoctorReport(
        schema="doctor.v3",
        run_id=run_id,
        trace_id=run_id,
        status=status,
        outcome=status or "unknown",
        broken_hop=broken,
        summary=summary,
        mode="backend",
        hops=hops,
        journal_path=persistence_ref,
        consistency={
            "projection_seq": snapshot.as_of_seq,
            "persisted_seq": persisted_seq,
            "projection_seq_eq_persisted_seq": (
                None if persisted_seq < 0 else snapshot.as_of_seq == persisted_seq
            ),
        },
        factory={"ok": True, "tools_missing_plugin_state": []},
    )


__all__ = ["diagnose_session_projection"]
