"""Typed data contracts shared by legacy and Session Spine run diagnostics."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

TERMINAL_STATUSES = frozenset({"completed", "failed", "canceled"})
OPEN_STATUSES = frozenset({"running", "waiting_input"})
TOOL_TERMINAL_EVENTS = frozenset({"ToolInvoked", "ToolDenied"})
RUN_FINISHED_EVENTS = frozenset({"AgentRunFinished", "TeamRunFinished"})


@dataclass(frozen=True, slots=True)
class HopVerdict:
    """One hop's pass, fail, or unavailable result in a doctor report."""

    ok: bool | None
    detail: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """Serialize a hop result for the Gateway response wire."""
        payload: dict[str, Any] = {"ok": self.ok}
        if self.detail:
            payload["detail"] = self.detail
        payload.update(self.extra)
        return payload


@dataclass(frozen=True, slots=True)
class DoctorReport:
    """Stable doctor.v2 response assembled from one diagnostic read model."""

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
        """Serialize a complete report for the Gateway response wire."""
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
class JsonlScan:
    """Facts derived from one legacy run's JSONL journal without live state."""

    last_seq: int
    counts: dict[str, int]
    missing_plugin_state: tuple[str, ...]
    unpaired_tools: tuple[str, ...]
    has_finished: bool
    journal_status: str
    exists: bool
    rows: int
    output_text: str
    output_text_explicit: bool
    finished_error: str
    tool_total: int
    tool_success: int
    max_consecutive_fail: int
    has_attachment: bool


__all__ = [
    "OPEN_STATUSES",
    "RUN_FINISHED_EVENTS",
    "TERMINAL_STATUSES",
    "TOOL_TERMINAL_EVENTS",
    "DoctorReport",
    "HopVerdict",
    "JsonlScan",
]
