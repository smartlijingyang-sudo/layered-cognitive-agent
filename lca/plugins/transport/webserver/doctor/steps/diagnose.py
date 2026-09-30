"""Doctor.v3 step-tree 装配入口(ADR-0164 草案 Phase 4)。

输入: JournalDocument(或直接 path)。
输出: DoctorReport(schema="doctor.v3", mode=backend|ui)。

Hops:
  - H1: journal.json 是否存在 + 可读
  - H2: step 闭合完整性(所有 step.outcome 非 None)
  - H3: 步骤顺序连续(step_index 1..N 无跳号)
  - H4: ui-mode 才检查(前端是否能到达 run)
  - H5: ui-mode 才检查(前端能否渲染产出)
  - H6: 是否有可观察 output / file
  - H7: 工具成功率 +是否有失败 step
  - H8 (新): 步骤因果链完整性——每 step 的 prior_summary_chain
    末元素 == 上 step 的 reflect.summary;不一致 → ok=False
  - H-xref (ADR-0176 D5): journal ⇄ spine 跨源一致性 hop
    (body.tool.execute.start 数 > 0 但 journal.steps[*].tool_call 为 0,
     llm.call.end 数 > 0 但 journal.totals.steps == 0,等)
  - H-fold (ADR-0185 PR-4): doctor fold-only 检查——
    诊断是否每 step 都能通过 :func:`fold_model_visible` 从 spine ledger
    重建;无 fold 时 ok=None(unavailable),不再读 model_visible sidecar。

不做的事:
    - 不读 evidence(由 reader 按需 fetch)。
    - 不发请求(doctor 是 passive 检查)。
    - 不执行 LLM / tool(只读 fold 模块 + spine ledger)。
"""

from __future__ import annotations

from pathlib import Path

from lca.contracts.models.observability.journal.doc import JournalDocument
from lca.infrastructure.observability.journal.step.reader import read_step_document
from lca.plugins.transport.webserver.doctor.models import (
    DoctorMode,
    DoctorReport,
    HopVerdict,
)
from lca.plugins.transport.webserver.doctor.steps.hops import (
    _hop_h1,
    _hop_h2,
    _hop_h3,
    _hop_h4,
    _hop_h5,
    _hop_h6,
    _hop_h7,
    _hop_h8,
    _hop_h_fold,
    _hop_h_mv_journal,
    _hop_h_phase,
    _hop_h_seg,
    _hop_h_ssot,
    _hop_h_xref,
    _summary,
)
from lca.plugins.transport.webserver.doctor.steps.scan import (
    _scan_fold,
    _scan_step_doc,
    _scan_xref,
)


def diagnose_step_tree(
    journal_path: Path | str,
    *,
    mode: DoctorMode = "backend",
) -> DoctorReport:
    """Build doctor.v3 from a step-tree journal.

    Parameters:
        journal_path: 指向 journal.json(支持 str / Path)
        mode: backend / ui(决定 H4/H5 是否计入)

    Returns:
        DoctorReport(schema="doctor.v3", ...)
    """
    path = Path(journal_path)
    scan = _scan_step_doc(path)
    run_id = path.parent.name  # traces/runs/<run_id>/journal.json
    doc: JournalDocument | None = None
    trace_id = ""
    if scan.exists:
        try:
            doc = read_step_document(path)
            run_id = doc.run_id or run_id
            trace_id = doc.trace_id
        except Exception as exc:
            import structlog

            _log = structlog.get_logger("lca.doctor.step_check")
            _log.debug("scan_failed", path=str(path), error=str(exc))
            doc = None
    # ADR-0176 D5:H-xref 需要 spine ledger(SSOT 解析)+ manifest.json。
    # SSOT 解析需要 run_id:spine_filename_for_run(run_id)派生主路径
    # (PR-4 收口,不再有 legacy 兜底)。
    xref_scan = _scan_xref(path.parent, run_id, scan)
    # ADR-0185 PR-3.1:doctor fold 优先双轨(``fold_model_visible`` →
    # ``<run_dir>/model_visible/`` → journal 推导)。fold scan 镜像
    # :func:`StandardCursor.at` 优先级,落地 ``StepScan.fold_*``。
    fold_scan = _scan_fold(path.parent, run_id, xref_scan, doc)
    status = scan.outcome or "unknown"
    hops: dict[str, HopVerdict] = {
        "H1": _hop_h1(scan),
        "H2": _hop_h2(scan),
        "H3": _hop_h3(scan),
        "H4": _hop_h4(mode),
        "H5": _hop_h5(mode, scan),
        "H6": _hop_h6(scan),
        # H7 多源对账(回归锁 run_1f5360d2fa47):需要 spine counts,
        # 因此走 xref_scan 而非 scan。
        "H7": _hop_h7(xref_scan),
        "H8": _hop_h8(scan),
        "H-seg": _hop_h_seg(scan),
        "H-phase": _hop_h_phase(scan),
        "H-xref": _hop_h_xref(xref_scan),
        "H-ssot": _hop_h_ssot(xref_scan),
        "H-mv-journal": _hop_h_mv_journal(xref_scan),
        "H-fold": _hop_h_fold(fold_scan),
    }
    broken = next((name for name, hop in hops.items() if hop.ok is False), None)
    factory = {"ok": True, "tools_missing_plugin_state": []}
    return DoctorReport(
        schema="doctor.v3",
        run_id=run_id,
        trace_id=trace_id,
        status=status,
        outcome=scan.outcome or "unknown",
        broken_hop=broken,
        summary=_summary(broken, hops, scan),
        mode=mode,
        hops=hops,
        journal_path=str(path),
        consistency={
            "total_steps": scan.total_steps,
            "duration_ms": scan.duration_ms,
            "totals_segments": scan.totals_segments,
            "totals_phases": scan.totals_phases,
            "spine_event_total": xref_scan.spine_event_total,
            "flush_errors": list(xref_scan.flush_errors),
            "tool_schema_count": xref_scan.tool_schema_count,
            "tool_schema_empty_count": xref_scan.tool_schema_empty_count,
            "tool_schema_source": xref_scan.tool_schema_source,
            "phase_fold_objective_anomalies": list(xref_scan.phase_fold_objective_anomalies),
            "fold_source": fold_scan.fold_source,
            "fold_attempted": fold_scan.fold_attempted,
            "fold_hits": fold_scan.fold_hits,
            "fold_misses": fold_scan.fold_misses,
            "fold_step_hits": list(fold_scan.fold_step_hits),
            "fold_step_misses": list(fold_scan.fold_step_misses),
        },
        factory=factory,
    )


__all__ = ["diagnose_step_tree"]
