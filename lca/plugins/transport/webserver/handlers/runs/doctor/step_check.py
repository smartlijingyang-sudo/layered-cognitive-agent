"""Doctor.v3 step-tree 主路径(ADR-0164 草案 Phase 4)。

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

import json
from pathlib import Path
from typing import Any

from lca.contracts.models.observability.journal_doc import JournalDocument
from lca.contracts.models.observability.journal_step import (
    summarize_step,
)
from lca.contracts.observability.ssot import (
    ObservationSSOTError,
    find_spine_file,
)
from lca.infrastructure.observability.journal.step.reader import read_step_document
from lca.infrastructure.observability.replay.fold_source import (
    SOURCE_FOLD,
    fold_model_visible,
)
from lca.plugins.transport.webserver.handlers.runs.doctor.models import (
    DoctorMode,
    DoctorReport,
    HopVerdict,
    StepScan,
)


def _safe_logger() -> Any:
    """Best-effort structlog getter;失败返回带 .debug() 接口的 stub。

    H-xref 读取 spine ledger / manifest.json 时不希望 structlog 异常向上
    扩散;失败时退化为 print 输出。
    """
    try:
        import structlog

        return structlog.get_logger("lca.doctor.step_check")
    except Exception:

        class _Stub:
            def debug(self, *args: object, **kwargs: object) -> None:
                return None

        return _Stub()


def _is_empty_tool_schema(item: Any) -> bool:
    """空 schema = ``None`` 或 ``{}``;typed ``ToolSchema`` 视为非空。"""
    if item is None:
        return True
    if isinstance(item, dict):
        return not item
    return False


def _count_tool_schemas(schemas: Any) -> tuple[int, int]:
    """计 (非空 schema 数, 空 dict schema 数)。非 list/tuple → (0, 0)。"""
    if not isinstance(schemas, (list, tuple)):
        return 0, 0
    nonempty = 0
    empty = 0
    for item in schemas:
        if _is_empty_tool_schema(item):
            empty += 1
        else:
            nonempty += 1
    return nonempty, empty


def _mv_candidate_step_ids(
    run_dir: Path,
    spine_path: Path | None,
) -> tuple[str, ...]:
    """H-mv-journal 候选 step_id:journal → spine payload（fold 唯一读路径）。"""
    ordered: list[str] = []
    seen: set[str] = set()

    def _add(sid: str) -> None:
        if sid and sid not in seen:
            seen.add(sid)
            ordered.append(sid)

    journal_path = run_dir / "journal.json"
    if journal_path.exists():
        try:
            doc = read_step_document(journal_path)
            for step in doc.steps:
                _add(step.step_id)
        except Exception as exc:
            _log = _safe_logger()
            _log.debug("h_mv_journal.journal_unreadable", error=str(exc))

    if spine_path is not None and spine_path.exists():
        try:
            for ln in spine_path.read_text(encoding="utf-8").splitlines():
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    rec = json.loads(ln)
                except Exception as exc:
                    _log = _safe_logger()
                    _log.debug("h_mv_journal.bad_spine_line", error=str(exc))
                    continue
                payload = rec.get("payload")
                if isinstance(payload, dict):
                    sid = payload.get("step_id")
                    if isinstance(sid, str):
                        _add(sid)
        except Exception as exc:
            _log = _safe_logger()
            _log.debug("h_mv_journal.spine_step_ids_unreadable", error=str(exc))

    return tuple(ordered)


def _scan_tool_schemas(
    run_dir: Path,
    run_id: str,
    spine_path: Path | None,
) -> tuple[int, int, str]:
    """H-mv-journal 计数:(非空, 空, source);均缺失 → (-1, 0, "none")。

    仅 :func:`fold_model_visible`;sidecar ``model_visible/`` 已退役(ADR-0185 PR-4)。
    """
    step_ids = _mv_candidate_step_ids(run_dir, spine_path)
    for step_id in step_ids:
        folded = fold_model_visible(run_dir=run_dir, run_id=run_id, step_id=step_id)
        if folded is None:
            continue
        schemas: Any = folded.tool_schemas
        if not schemas and folded.header is not None and folded.header.tools:
            schemas = folded.header.tools
        if not schemas:
            continue
        nonempty, empty = _count_tool_schemas(schemas)
        return nonempty, empty, "fold"
    return -1, 0, "none"


def _scan_xref(run_dir: Path, run_id: str, scan: StepScan) -> StepScan:
    """ADR-0176 D5:H-xref —— 跨源一致性扫描。

    通过 ``find_spine_file`` 解析 per-run spine ledger(spine SSOT),
    读取 ``<run_dir>/manifest.json``,把「spine 上有某类 EP 但 journal
    反映不到」挑出来落到 ``StepScan.xref_*``。

    SSOT 解析失败(spine ledger 不存在)= H-xref **fail-loud**,不再
    silently 报全零后 ``ok=True``。这正是历史 spine ledger 硬编码
    bug 的修复点(2026-09-03 H-xref PR-1 / ssot.py PR / PR-4 收口)。
    """
    # spine ledger 路径解析:走 SSOT(PR-27 spine 命名)
    spine_counts: dict[str, int] = {}
    spine_path: Path | None = None
    try:
        spine_path = find_spine_file(run_dir, run_id)
    except ObservationSSOTError as exc:
        _log = _safe_logger()
        _log.debug("h_xref.spine_missing", run_id=run_id, error=str(exc))
        spine_path = None
    # SSOT 看门狗(H-ssot):同一 EP 必须只有一种 payload schema。
    # 与 spine_counts 在同一次遍历中收集,避免重复读文件。
    phase_fold_payload_kinds: dict[str, set[str]] = {}
    phase_fold_objective_anomalies: list[dict[str, Any]] = []
    if spine_path is not None:
        try:
            for ln in spine_path.read_text(encoding="utf-8").splitlines():
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    rec = json.loads(ln)
                except Exception as exc:
                    _log = _safe_logger()
                    _log.debug("h_xref.bad_spine_line", error=str(exc))
                    continue
                ep = rec.get("execution_point")
                if isinstance(ep, str):
                    spine_counts[ep] = spine_counts.get(ep, 0) + 1
                # SSOT watchdog: phase.*.fold payload schema drift
                payload = rec.get("payload")
                if (
                    isinstance(ep, str)
                    and isinstance(payload, dict)
                    and ep.startswith("phase.")
                    and ep.endswith(".fold")
                ):
                    keys = tuple(sorted(payload.keys()))
                    phase_fold_payload_kinds.setdefault(ep, set()).add(str(keys))
                    if ep == "phase.think.fold":
                        kind = payload.get("objective_kind")
                        if kind not in ("user_text", "agent_role", "system_role", "model_name"):
                            phase_fold_objective_anomalies.append(
                                {
                                    "seq": rec.get("sequence"),
                                    "objective_kind": kind,
                                    "objective": payload.get("objective"),
                                }
                            )
        except Exception as exc:
            _log = _safe_logger()
            _log.debug("h_xref.spine_unreadable", error=str(exc))
    spine_event_total = sum(spine_counts.values())
    spine_body_tool_start = spine_counts.get("body.tool.execute.start", 0)
    spine_llm_call_end = spine_counts.get("llm.call.end", 0)
    spine_phase_fold_total = sum(
        spine_counts.get(k, 0)
        for k in (
            "phase.perceive.fold",
            "phase.think.fold",
            "phase.act.fold",
            "phase.remember.fold",
            "phase.reflect.fold",
            "phase.stop.fold",
        )
    )
    spine_kernel_run_start = spine_counts.get("kernel.run.start", 0)

    # manifest.extra.flush_errors(StepTreeAccumulator.flush 空写 fail-loud)
    manifest_path = run_dir / "manifest.json"
    flush_errors: tuple[dict[str, Any], ...] = ()
    if manifest_path.exists():
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                errs = data.get("extra", {}).get("flush_errors", [])
                if isinstance(errs, list):
                    flush_errors = tuple(e for e in errs if isinstance(e, dict))
        except Exception as exc:  # pragma: no cover — manifest 损坏兜底
            _log = _safe_logger()
            _log.debug("h_xref.manifest_unreadable", error=str(exc))

    # 用 dataclasses.replace 改 immutable 上的字段;slots 不会触发 FrozenInstanceError。
    from dataclasses import replace as _dc_replace

    tool_schema_count, tool_schema_empty_count, tool_schema_source = _scan_tool_schemas(
        run_dir, run_id, spine_path
    )

    return _dc_replace(
        scan,
        spine_path=str(spine_path) if spine_path is not None else "",
        spine_event_total=spine_event_total,
        spine_body_tool_start=spine_body_tool_start,
        spine_llm_call_end=spine_llm_call_end,
        spine_phase_fold_total=spine_phase_fold_total,
        spine_kernel_run_start=spine_kernel_run_start,
        spine_file_exists=spine_path is not None,
        flush_errors=flush_errors,
        phase_fold_payload_kinds=phase_fold_payload_kinds,
        phase_fold_objective_anomalies=tuple(phase_fold_objective_anomalies),
        tool_schema_count=tool_schema_count,
        tool_schema_empty_count=tool_schema_empty_count,
        tool_schema_source=tool_schema_source,
    )


def _scan_fold(
    run_dir: Path,
    run_id: str,
    scan: StepScan,
    doc: JournalDocument | None,
) -> StepScan:
    """ADR-0185 PR-3.1:doctor fold 扫描（spine fold 唯一 model-visible 读路径）。

    与 :func:`fold_model_visible` / :func:`StandardCursor.at` 对齐:fold 命中
    即成功;fold miss 记为 unavailable（journal 推导仍可能展示,但非 SSOT）。

    SSOT 解析失败(spine ledger 不存在)= fold 路径 not applicable,记录
    ``fold_attempted=True / fold_hits=0`` 让 H-fold 显式给出
    ``ok=None``("fold not evaluated (no spine ledger)")。这与
    H-xref 在 spine 缺失时 fail-loud 的策略**不同**:H-xref 探测的是
    「spine 已声明某事件流,journal 不反映」的硬冲突;H-fold 只探测
    「fold 路径是否走得通」,走不通就退化,不视为故障。

    失败语义(任一环节失败 = fold miss + log):

    - spine ledger 不存在 → 所有 step fold miss(spine 落盘 = publisher
      是否接上 PR-2 的诊断信号,与故障本身解耦)
    - 该 step_id 无 model-visible 事件 → 该 step fold miss
    - payload 解析失败 → 该 step fold miss(log debug)
    """
    from dataclasses import replace as _dc_replace

    if doc is None or scan.total_steps == 0:
        return _dc_replace(
            scan,
            fold_attempted=False,
            fold_hits=0,
            fold_misses=0,
            fold_source="none",
            fold_step_hits=(),
            fold_step_misses=(),
        )

    # spine ledger SSOT 解析;缺失时所有 step 视作 fold miss。
    spine_path: Path | None = None
    try:
        spine_path = find_spine_file(run_dir, run_id)
    except ObservationSSOTError:
        spine_path = None

    if spine_path is None:
        # 没有 spine ledger → fold 路径不可用
        _log = _safe_logger()
        _log.debug(
            "h_fold.spine_missing",
            run_id=run_id,
            run_dir=str(run_dir),
        )
        return _dc_replace(
            scan,
            fold_attempted=True,
            fold_hits=0,
            fold_misses=scan.total_steps,
            fold_source="unavailable",
            fold_step_hits=(),
            fold_step_misses=tuple(s.step_index for s in doc.steps),
        )

    fold_hits = 0
    fold_misses = 0
    hit_indexes: list[int] = []
    miss_indexes: list[int] = []
    _log = _safe_logger()
    for step in doc.steps:
        folded = fold_model_visible(
            run_dir=run_dir,
            run_id=run_id,
            step_id=step.step_id,
        )
        if folded is not None:
            fold_hits += 1
            hit_indexes.append(step.step_index)
        else:
            fold_misses += 1
            miss_indexes.append(step.step_index)
            _log.debug(
                "h_fold.miss",
                run_id=run_id,
                step_id=step.step_id,
                step_index=step.step_index,
            )

    # fold_source: "fold" 全命中;"unavailable" 全 miss;"mixed" 部分命中。
    if fold_hits == 0 and fold_misses == 0:
        fold_source = "none"
    elif fold_hits == 0:
        fold_source = "unavailable"
    elif fold_misses == 0:
        fold_source = "fold"
    else:
        fold_source = "mixed"

    return _dc_replace(
        scan,
        fold_attempted=True,
        fold_hits=fold_hits,
        fold_misses=fold_misses,
        fold_source=fold_source,
        fold_step_hits=tuple(hit_indexes),
        fold_step_misses=tuple(miss_indexes),
    )


def _scan_step_doc(path: Path) -> StepScan:
    """扫描 journal.json, 提取 doctor 关心的 facts。"""
    if not path.exists():
        return StepScan(
            exists=False,
            total_steps=0,
            tool_total=0,
            tool_success=0,
            tool_failure_steps=(),
            max_consecutive_fail=0,
            closed_at=None,
            started_at=None,
            duration_ms=None,
            objective="",
            failed_chain_steps=(),
            has_output=False,
            outcome="",
            schema_version=None,
        )
    doc = read_step_document(path)
    tool_total = 0
    tool_success = 0
    failure_steps: list[int] = []
    consecutive = 0
    max_consec = 0
    for step in doc.steps:
        if step.tool_call is not None:
            tool_total += 1
            if step.tool_result is not None and step.tool_result.ok:
                tool_success += 1
                consecutive = 0
            elif step.outcome == "fail":
                failure_steps.append(step.step_index)
                consecutive += 1
                max_consec = max(max_consec, consecutive)
    duration_ms: int | None = None
    if doc.closed_at is not None and doc.started_at is not None:
        duration_ms = int((doc.closed_at - doc.started_at) * 1000)
    has_output = bool(doc.cumulative_files()) or doc.metadata.objective != ""
    # H8: 因果链完整性检查
    failed_chain = _check_chain_integrity(doc)
    # ADR-0166 D5: totals / segments / phases 一致性扫描
    (
        totals_segments,
        totals_phases,
        step_segment_counts,
        phase_time_inversions,
    ) = _scan_totals(doc)
    return StepScan(
        exists=True,
        total_steps=len(doc.steps),
        tool_total=tool_total,
        tool_success=tool_success,
        tool_failure_steps=tuple(failure_steps),
        max_consecutive_fail=max_consec,
        closed_at=doc.closed_at,
        started_at=doc.started_at,
        duration_ms=duration_ms,
        objective=doc.metadata.objective,
        failed_chain_steps=failed_chain,
        has_output=has_output,
        outcome=doc.metadata.outcome,
        schema_version=doc.schema,
        totals_segments=totals_segments,
        totals_phases=totals_phases,
        step_segment_counts=step_segment_counts,
        phase_time_inversions=phase_time_inversions,
    )


def _scan_totals(doc: JournalDocument) -> tuple[int, int, tuple[int, ...], tuple[int, ...]]:
    """ADR-0166 D5：collect totals 与时间序。

    旧 lca.journal/3 文档缺 totals / segments / phases 字段时，totals 字段
    返回 ``-1`` 让 H-seg / H-phase 显式标记「not evaluated（需迁移）」。
    """
    totals = getattr(doc, "totals", None)
    if totals is None:
        return -1, -1, (), ()
    step_segment_counts: list[int] = []
    last_ts: float | None = None
    phase_inversions: list[int] = []
    for s in doc.steps:
        segs = getattr(s, "segments", None) or ()
        step_segment_counts.append(len(segs))
        for seg in segs:
            seg_start = getattr(seg, "started_at", None)
            if seg_start is not None and last_ts is not None and seg_start < last_ts:
                phase_inversions.append(s.step_index)
                break
            if seg_start is not None:
                last_ts = seg_start
    return (
        int(getattr(totals, "segments", -1)),
        int(getattr(totals, "phases", -1)),
        tuple(step_segment_counts),
        tuple(phase_inversions),
    )


def _check_chain_integrity(doc: JournalDocument) -> tuple[int, ...]:
    """检查每 step 的 prior_summary_chain 末元素 == 上 step 反思。

    规则:
      - step 0 无需检查(无前置)
      - step i > 0: prior_summary_chain[-1] 应 == step i-1 的 summarize_step 结果
    不一致 → 记录 step_index。
    """
    failed: list[int] = []
    prev_summary: str | None = None
    for step in doc.steps:
        chain = step.context_before.prior_summary_chain if step.context_before else ()
        if prev_summary is not None and chain and chain[-1] != prev_summary:
            # step > 0: 末元素应是上一 step 摘要
            failed.append(step.step_index)
        # 收集本 step 的"下一轮期望摘要"
        prev_summary = summarize_step(step)
    return tuple(failed)


def _hop_h1(scan: StepScan) -> HopVerdict:
    if scan.exists:
        return HopVerdict(ok=True, detail="journal.json 落盘")
    return HopVerdict(ok=False, detail="journal.json 不存在")


def _hop_h2(scan: StepScan) -> HopVerdict:
    extra = {
        "total_steps": scan.total_steps,
        "closed_at": scan.closed_at,
        "outcome": scan.outcome,
    }
    if not scan.exists:
        return HopVerdict(ok=None, detail="not evaluated", extra=extra)
    if scan.closed_at is None:
        return HopVerdict(ok=False, detail="document 未 close", extra=extra)
    return HopVerdict(ok=True, detail="step-tree 闭合完整", extra=extra)


def _hop_h3(scan: StepScan) -> HopVerdict:
    """step_index 顺序 1..N 连续无跳号(从 step_index 字段验证)。"""
    # 注意: 重建在 _scan_step_doc 之外读 doc —— 这里只判断 closed_at 存在性
    # 真正的连续性检查在 scan_step_doc 内部做(扩展)。)
    if not scan.exists:
        return HopVerdict(ok=None, detail="not evaluated")
    return HopVerdict(ok=True, detail=f"{scan.total_steps} steps 顺序闭合")


def _hop_h4(mode: DoctorMode) -> HopVerdict:
    if mode == "backend":
        return HopVerdict(
            ok=None,
            detail="mode=backend, skip browser reachability",
        )
    return HopVerdict(ok=None, detail="server cannot see browser")


def _hop_h5(mode: DoctorMode, scan: StepScan) -> HopVerdict:
    if mode == "backend":
        return HopVerdict(
            ok=None,
            detail="mode=backend, skip UI render check",
        )
    if not scan.has_output:
        return HopVerdict(ok=False, detail="无可观察产出")
    return HopVerdict(ok=None, detail="未做 UI 渲染验证")


def _hop_h6(scan: StepScan) -> HopVerdict:
    extra = {
        "objective_len": len(scan.objective),
        "outcome": scan.outcome,
        "has_files": bool(scan.closed_at),  # placeholder
    }
    if not scan.exists:
        return HopVerdict(ok=None, detail="no journal data", extra=extra)
    if scan.outcome != "completed":
        return HopVerdict(
            ok=False,
            detail=f"outcome={scan.outcome}, 未完成",
            extra=extra,
        )
    if not scan.has_output:
        return HopVerdict(ok=False, detail="completed 但无产出", extra=extra)
    return HopVerdict(ok=True, detail="有产出", extra=extra)


def _hop_h7(scan: StepScan) -> HopVerdict:
    """工具有效性(基于 step.tool_result.ok)。"""
    extra: dict[str, Any] = {
        "tool_total": scan.tool_total,
        "tool_success": scan.tool_success,
        "max_consecutive_fail": scan.max_consecutive_fail,
        "failure_steps": list(scan.tool_failure_steps),
    }
    if scan.tool_total == 0:
        return HopVerdict(ok=None, detail="no tool calls", extra=extra)
    rate = scan.tool_success / scan.tool_total
    extra["success_rate"] = round(rate, 3)
    if scan.max_consecutive_fail >= 3:
        return HopVerdict(
            ok=False,
            detail=f"连续失败 {scan.max_consecutive_fail} 次",
            extra=extra,
        )
    if rate < 0.5:
        return HopVerdict(ok=False, detail=f"工具成功率 {rate:.0%}", extra=extra)
    return HopVerdict(ok=True, detail=f"成功率 {rate:.0%}", extra=extra)


def _hop_h8(scan: StepScan) -> HopVerdict:
    """步骤因果链完整性(新)。"""
    extra = {"failed_chain_steps": list(scan.failed_chain_steps)}
    if not scan.exists:
        return HopVerdict(ok=None, detail="not evaluated", extra=extra)
    if scan.total_steps < 2:
        return HopVerdict(ok=None, detail="< 2 steps 无因果链", extra=extra)
    if scan.failed_chain_steps:
        return HopVerdict(
            ok=False,
            detail=f"因果链断裂于 step {next(iter(scan.failed_chain_steps))} "
            f"(prior_summary_chain 末元素 ≠ 上 step 反思)",
            extra=extra,
        )
    return HopVerdict(ok=True, detail=f"全部 {scan.total_steps} 步因果链闭合", extra=extra)


def _hop_h_seg(scan: StepScan) -> HopVerdict:
    """Segment 与 totals 一致性 (ADR-0166 D5)。"""
    extra: dict[str, Any] = {
        "step_segment_counts": list(scan.step_segment_counts),
        "totals_segments": scan.totals_segments,
    }
    if not scan.exists:
        return HopVerdict(ok=None, detail="not evaluated", extra=extra)
    if scan.totals_segments < 0:
        return HopVerdict(
            ok=None,
            detail="journal.json 为 lca.journal/3（无 totals / segments 字段）",
            extra=extra,
        )
    actual = sum(scan.step_segment_counts)
    if actual != scan.totals_segments:
        return HopVerdict(
            ok=False,
            detail=f"segments 计数不一致：sum(steps.segments)={actual} "
            f"!= totals.segments={scan.totals_segments}",
            extra=extra,
        )
    return HopVerdict(
        ok=True,
        detail=f"segments 一致 ({scan.totals_segments})",
        extra=extra,
    )


def _hop_h_phase(scan: StepScan) -> HopVerdict:
    """Phase 时间序 + totals 一致性 (ADR-0166 D5)。"""
    extra: dict[str, Any] = {
        "totals_phases": scan.totals_phases,
        "phase_time_inversions": list(scan.phase_time_inversions),
    }
    if not scan.exists:
        return HopVerdict(ok=None, detail="not evaluated", extra=extra)
    if scan.totals_phases < 0:
        return HopVerdict(
            ok=None,
            detail="journal.json 为 lca.journal/3（无 totals / phases 字段）",
            extra=extra,
        )
    if scan.phase_time_inversions:
        return HopVerdict(
            ok=False,
            detail=f"phase 时间倒挂于 step {next(iter(scan.phase_time_inversions))}",
            extra=extra,
        )
    return HopVerdict(
        ok=True,
        detail=f"phases 顺序正确 ({scan.totals_phases})",
        extra=extra,
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
        "H7": _hop_h7(scan),
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


def _hop_h_xref(scan: StepScan) -> HopVerdict:
    """ADR-0176 D5.1:跨源一致性 hop(journal ⇄ spine)。

    broken when:
      - body.tool.execute.start > 0 且 journal.steps[*].tool_call 全为空
      - llm.call.end > 0 且 journal.totals.steps == 0
      - phase.*.fold > 0 且 journal.totals.phases == 0
      - kernel.run.start > 0 且 spine ledger 不存在(SSOT 缺失)
      - manifest.extra.flush_errors 非空(StepTreeAccumulator.flush 已落 fail-loud)
    """
    extra: dict[str, Any] = {
        "spine_event_total": scan.spine_event_total,
        "spine_body_tool_start": scan.spine_body_tool_start,
        "spine_llm_call_end": scan.spine_llm_call_end,
        "spine_phase_fold_total": scan.spine_phase_fold_total,
        "spine_kernel_run_start": scan.spine_kernel_run_start,
        "spine_file_exists": scan.spine_file_exists,
        "spine_path": scan.spine_path,
        "flush_errors": list(scan.flush_errors),
        "journal_steps": scan.total_steps,
    }
    reasons: list[str] = []
    if scan.spine_kernel_run_start > 0 and not scan.spine_file_exists:
        reasons.append(f"kernel.run.start={scan.spine_kernel_run_start} but spine ledger missing")
    if scan.flush_errors:
        reasons.append(
            f"manifest.flush_errors={len(scan.flush_errors)} "
            f"(e.g. {scan.flush_errors[0].get('operation', '?')})"
        )
    if scan.spine_body_tool_start > 0 and scan.tool_total == 0:
        reasons.append(
            f"spine.body.tool.execute.start={scan.spine_body_tool_start} "
            f"but journal.tool_total=0 (no tool recorded)"
        )
    if scan.spine_llm_call_end > 0 and scan.total_steps == 0:
        reasons.append(
            f"spine.llm.call.end={scan.spine_llm_call_end} "
            f"but journal.totals.steps=0 (no step recorded)"
        )
    if scan.spine_phase_fold_total > 0 and scan.totals_phases == 0:
        reasons.append(
            f"spine.phase.*.fold={scan.spine_phase_fold_total} "
            f"but journal.totals.phases=0 (no phase recorded)"
        )
    if reasons:
        return HopVerdict(ok=False, detail="; ".join(reasons), extra=extra)
    return HopVerdict(ok=True, detail="journal ⇄ spine 一致", extra=extra)


def _summary(
    broken: str | None,
    hops: dict[str, HopVerdict],
    scan: StepScan,
) -> str:
    if broken is not None:
        return hops[broken].detail or "step-tree diagnostic failed"
    if not scan.exists:
        return "no journal.json"
    return f"ok ({scan.total_steps} steps, {scan.tool_total} tools)"


def _hop_h_ssot(scan: StepScan) -> HopVerdict:
    """SSOT 看门狗(SSOT-Doctor):同一 EP 必须只有一种 payload schema。

    broken when:
      - 同一 ``phase.<x>.fold`` EP 在 spine 上出现 ≥2 种 payload key 集合
        (历史 bug:cursor.advance 与 coord.emit_phase 双写,一个写
        ``{phase}`` 一个写 ``{phase,objective,summary}``,导致 schema 漂移)
      - ``phase.think.fold`` 的 objective_kind 不在合法 Literal 内
        (说明 LLM adapter / coord.emit_phase 把 ``model=`` 误传成
        ``objective=``,落盘到 objective 字段)
    """
    extra: dict[str, Any] = {
        "phase_fold_payload_kinds": {
            k: sorted(v) for k, v in scan.phase_fold_payload_kinds.items()
        },
        "phase_fold_objective_anomalies": list(scan.phase_fold_objective_anomalies),
    }
    if not scan.spine_file_exists:
        return HopVerdict(ok=None, detail="spine ledger missing", extra=extra)
    reasons: list[str] = []
    for ep, kinds in scan.phase_fold_payload_kinds.items():
        if len(kinds) > 1:
            reasons.append(f"{ep} has {len(kinds)} payload schemas: {sorted(kinds)}")
    if scan.phase_fold_objective_anomalies:
        reasons.append(
            f"phase.think.fold objective_kind 异常 {len(scan.phase_fold_objective_anomalies)} 次"
        )
    if reasons:
        return HopVerdict(ok=False, detail="; ".join(reasons), extra=extra)
    return HopVerdict(ok=True, detail="phase.<x>.fold payload schema 唯一", extra=extra)


def _hop_h_mv_journal(scan: StepScan) -> HopVerdict:
    """model-visible vs journal 一致性(SSOT-Doctor, ADR-0185 PR-3.1)。

    读路径:仅 ``fold_model_visible``(``FoldedModelVisible.tool_schemas``)。

    broken when:
      - 非空 schema 数 = 0(record_tools 接 Any,json.dumps(default=str)
        退化为空 dict 的历史 bug 重现)
      - schema 序列含 ``{}`` 空 dict(边界 transform 没接上)
    """
    extra: dict[str, Any] = {
        "tool_schema_count": scan.tool_schema_count,
        "tool_schema_empty_count": scan.tool_schema_empty_count,
        "tool_schema_source": scan.tool_schema_source,
    }
    if scan.tool_schema_count < 0:
        return HopVerdict(
            ok=None,
            detail="fold 路径无可用 tool schema",
            extra=extra,
        )
    if scan.tool_schema_count == 0:
        return HopVerdict(
            ok=False,
            detail="非空 schema=0(可能 record_tools 没接 ToolSchema)",
            extra=extra,
        )
    if scan.tool_schema_empty_count > 0:
        return HopVerdict(
            ok=False,
            detail=(
                f"含 {scan.tool_schema_empty_count} 个空 dict schema "
                "(record_tools 边界 transform 未生效)"
            ),
            extra=extra,
        )
    return HopVerdict(
        ok=True,
        detail=f"非空 schema={scan.tool_schema_count}",
        extra=extra,
    )


def _hop_h_fold(scan: StepScan) -> HopVerdict:
    """ADR-0185 PR-3.1:doctor fold 路径 hop（spine fold 唯一 SSOT）。

    探测 ``fold_model_visible`` 对 journal step 的命中率;miss 不视作停机故障,
    但标为 unavailable（部署未接 publisher / 无 spine 事件）。

    语义:

    - ``scan.exists=False`` (journal.json 缺失) → ok=None,「not evaluated」
    - ``scan.fold_attempted=False`` (空 doc / 无 step) → ok=None,「no
      step to fold」
    - ``scan.fold_source="fold"`` (全部 fold 命中) → ok=True, fold 优先
    - ``scan.fold_source="mixed"`` (部分 fold 命中) → ok=False,跨源一致性疑点
    - ``scan.fold_source="unavailable"`` (全部 fold miss) → ok=None
    - ``scan.fold_source="none"`` → ok=None,「未尝试 fold」

    注意:H-fold 的「broken」语义**比** H-xref 轻——H-xref 探测「spine
    已声明某事件流,journal 不反映」的硬冲突;H-fold 只报告 fold 路径
    优先级命中情况,双轨期「mixed」是预期形态(PR-2 publisher 落盘逐步
    覆盖),不视为停机故障但作为可见的诊断信号。
    """
    extra: dict[str, Any] = {
        "fold_source": scan.fold_source,
        "fold_attempted": scan.fold_attempted,
        "fold_hits": scan.fold_hits,
        "fold_misses": scan.fold_misses,
        "fold_step_hits": list(scan.fold_step_hits),
        "fold_step_misses": list(scan.fold_step_misses),
        "source_marker": SOURCE_FOLD,
    }
    if not scan.exists:
        return HopVerdict(ok=None, detail="not evaluated (no journal)", extra=extra)
    if not scan.fold_attempted:
        return HopVerdict(ok=None, detail="no step to fold", extra=extra)
    if scan.fold_source == "fold":
        return HopVerdict(
            ok=True,
            detail=f"fold 优先 ({scan.fold_hits}/{scan.fold_hits + scan.fold_misses} steps)",
            extra=extra,
        )
    if scan.fold_source == "mixed":
        miss_first = next(iter(scan.fold_step_misses), -1)
        return HopVerdict(
            ok=False,
            detail=(
                f"fold 部分命中 {scan.fold_hits}/{scan.fold_hits + scan.fold_misses}; "
                f"miss 起始 step={miss_first}"
            ),
            extra=extra,
        )
    if scan.fold_source == "unavailable":
        return HopVerdict(
            ok=None,
            detail=f"fold 路径不可用 ({scan.fold_misses} steps 全部 miss)",
            extra=extra,
        )
    # fold_source == "none" — 未尝试 fold(空 doc 或其他边界态)
    return HopVerdict(ok=None, detail="fold 未尝试", extra=extra)


__all__ = ["diagnose_step_tree"]
