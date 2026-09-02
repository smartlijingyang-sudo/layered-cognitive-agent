"""Typed data contracts shared by step-tree and Session Spine run diagnostics.

ADR-0164 Phase 4 升级 doctor.v3:
  - ``schema`` 从 "doctor.v2" → "doctor.v3"。
  - 增 ``mode: Literal["backend", "ui"]`` —— backend 跳过 H4/H5;ui 全检。
  - 增 H8 "步骤因果链完整性" —— step_tree mode 下基于 prior_summary_chain
    检查每 step 是否引用上一 step 的 reflect 摘要。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

TERMINAL_STATUSES = frozenset({"completed", "failed", "canceled"})
OPEN_STATUSES = frozenset({"running", "waiting_input"})

DoctorMode = Literal["backend", "ui"]
"""doctor 模式:backend = 没浏览器/UI 不可视,跳过 H4/H5;ui = 完整流程检查。"""


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
    """doctor.v3 response — step-tree 主路径 + mode 区分。

    字段变更:
      - ``schema`` 永远 "doctor.v3"。
      - ``mode`` 显式标记("backend" / "ui"), reader 据此理解 H4/H5。
      - ``journal_path`` 指向 step-tree ``journal.json``(legacy jsonl 已下线)。
    """

    schema: str
    run_id: str
    trace_id: str
    status: str
    # outcome is the run-level terminal outcome (completed/failed/stopped/paused/
    # in_progress), mirrored from ``JournalMetadata.outcome``. 以前仅埋在
    # H6.extra.outcome 里,debug-run / manifest 消费方读到 null 是 bug;
    # 现在作为顶级字段对外暴露, wire consumers 不用再 hop 到 H6。
    outcome: str
    broken_hop: str | None
    summary: str
    mode: DoctorMode
    hops: dict[str, HopVerdict]
    journal_path: str
    consistency: dict[str, Any]
    factory: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        """Serialize a complete report for the Gateway response wire."""
        return {
            "schema": self.schema,
            "run_id": self.run_id,
            "trace_id": self.trace_id,
            "status": self.status,
            "outcome": self.outcome,
            "broken_hop": self.broken_hop,
            "summary": self.summary,
            "mode": self.mode,
            "hops": {name: hop.as_dict() for name, hop in self.hops.items()},
            "journal_path": self.journal_path,
            "consistency": self.consistency,
            "factory": self.factory,
        }


@dataclass(frozen=True, slots=True)
class StepScan:
    """Facts derived from one run's step-tree journal (lca.journal/3 / 3.1)。"""

    exists: bool
    total_steps: int
    tool_total: int
    tool_success: int
    tool_failure_steps: tuple[int, ...]  # step_index 列表
    max_consecutive_fail: int
    closed_at: float | None
    started_at: float | None
    duration_ms: int | None
    objective: str
    failed_chain_steps: tuple[int, ...]  # H8 失败: 因果链不一致的 step_index
    has_output: bool
    outcome: str
    schema_version: str | None  # None → 文件不存在
    # ADR-0166 D5: totals / segments / phases 一致性
    totals_segments: int = -1  # -1 → 旧 3.0 schema 缺字段
    totals_phases: int = -1
    step_segment_counts: tuple[int, ...] = ()
    phase_time_inversions: tuple[int, ...] = ()  # step_index 列表
    # ADR-0176 D5:H-xref 跨源扫描事实
    spine_path: str = ""
    spine_event_total: int = 0
    spine_body_tool_start: int = 0
    spine_llm_call_end: int = 0
    spine_phase_fold_total: int = 0
    spine_kernel_run_start: int = 0
    events_jsonl_exists: bool = False
    flush_errors: tuple[dict[str, Any], ...] = ()


__all__ = [
    "OPEN_STATUSES",
    "TERMINAL_STATUSES",
    "DoctorMode",
    "DoctorReport",
    "HopVerdict",
    "StepScan",
]
