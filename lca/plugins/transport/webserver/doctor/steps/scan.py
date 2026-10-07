"""StepScan 事实收集:journal / spine / fold 扫描(doctor.v3 数据面)。

包含:
  - ``_scan_step_doc`` / ``_scan_totals`` / ``_check_chain_integrity``:
    journal.json 读取与 StepScan 构造(H2/H3/H6/H7/H8/H-seg/H-phase 的事实源)
  - ``_scan_xref``(ADR-0176 D5):journal ⇄ spine 跨源一致性扫描
  - ``_scan_fold``(ADR-0185 PR-3.1/PR-4):fold-only 命中统计
  - ``_scan_tool_schemas`` / ``_mv_candidate_step_ids``:H-mv-journal tool schema 计数
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lca.contracts.models.observability.journal.doc import JournalDocument
from lca.contracts.models.observability.journal.step import (
    summarize_step,
)
from lca.contracts.observability.core.ssot import (
    ObservationSSOTError,
    find_spine_file,
)
from lca.infrastructure.observability.journal.step.reader import read_step_document
from lca.infrastructure.observability.replay.fold_source import fold_model_visible
from lca.plugins.transport.webserver.doctor.models import StepScan
from lca_kernel.events.compile.compiler import compiled_observability_plan


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


def _journal_closure_execution_points() -> frozenset[str]:
    """Journal-critical EPs from compiled observability plan (ADR-0198 P2)."""
    plan = compiled_observability_plan()
    if not plan.ok:
        return frozenset()
    return frozenset(
        spec.execution_point
        for spec in plan.closure_events
        if "projection.journal.step_tree" in spec.consumers
    )


def _phase_fold_execution_points() -> tuple[str, ...]:
    return tuple(
        ep
        for ep in sorted(_journal_closure_execution_points())
        if ep.startswith("phase.") and ep.endswith(".fold")
    )


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
    # H7 多源对账(回归锁 run_1f5360d2fa47):spine phase.tool.call.end.ok
    # 与 journal step.tool_result.ok 互相对账。第一性原则:成败字段
    # 不允许默认值,spine 写入 path 已声明 ``ok: bool``(spine.yaml)。
    spine_phase_tool_call_end_total = 0
    spine_phase_tool_call_end_ok_count = 0
    spine_phase_tool_call_end_failure_count = 0
    spine_tool_inv_ids: set[str] = set()
    spine_step_tool_counts: dict[Any, int] = {}
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
                # H7 多源对账:统计 phase.tool.call.end.ok 与 invocation_ids
                if (
                    isinstance(ep, str)
                    and ep == "phase.tool.call.end"
                    and isinstance(rec.get("payload"), dict)
                ):
                    payload = rec["payload"]
                    if "ok" in payload:
                        spine_phase_tool_call_end_total += 1
                        if payload["ok"] is True:
                            spine_phase_tool_call_end_ok_count += 1
                        elif payload["ok"] is False:
                            spine_phase_tool_call_end_failure_count += 1
                    inv_id = payload.get("invocation_id")
                    if isinstance(inv_id, str) and inv_id:
                        spine_tool_inv_ids.add(inv_id)
                    step_val = payload.get("step")
                    if step_val is not None:
                        spine_step_tool_counts[step_val] = (
                            spine_step_tool_counts.get(step_val, 0) + 1
                        )
                # SSOT watchdog: phase.*.fold payload schema drift
                payload = rec.get("payload")
                if (
                    isinstance(ep, str)
                    and isinstance(payload, dict)
                    and ep.startswith("phase.")
                    and ep.endswith(".fold")
                ):
                    keys = tuple(sorted(payload))
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
    spine_phase_fold_total = sum(spine_counts.get(k, 0) for k in _phase_fold_execution_points())
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
        spine_phase_tool_call_end_total=spine_phase_tool_call_end_total,
        spine_phase_tool_call_end_ok_count=spine_phase_tool_call_end_ok_count,
        spine_phase_tool_call_end_failure_count=spine_phase_tool_call_end_failure_count,
        spine_tool_invocation_ids=tuple(sorted(spine_tool_inv_ids)),
        spine_tool_forked=any(count > 1 for count in spine_step_tool_counts.values()),
        spine_tool_has_step_info=bool(spine_step_tool_counts),
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
            tool_ok_error_conflicts=(),
        )
    doc = read_step_document(path)
    tool_total = 0
    tool_success = 0
    failure_steps: list[int] = []
    consecutive = 0
    max_consec = 0
    # 回归锁 run_1f5360d2fa47:fold invariant 在生产路径上抛
    # FoldConsistencyError,但残留 journal 文件可能含历史矛盾样本。
    # doctor 仍要识别它们并报 H7.ok=False。
    tool_ok_error_conflicts: list[int] = []
    # PR-D: tool_total = distinct non-empty tool-call invocation_id count,
    # excluding phantom steps with empty invocation_id. tool_success counts
    # the subset of those call ids with at least one ok result, so the
    # success rate stays within [0, 1] even when tool_results carries extra
    # non-tool rows (e.g. decision.parse records).
    _tool_invocation_ids: set[str] = set()
    _tool_success_ids: set[str] = set()
    step_ids: list[str] = []
    step_indexes: list[int] = []
    for step in doc.steps:
        step_ids.append(step.step_id)
        step_indexes.append(step.step_index)

        # Collect tool calls (support both plural tool_calls and singular tool_call)
        calls: list[Any] = list(step.tool_calls) if step.tool_calls else []
        if not calls and step.tool_call is not None:
            calls = [step.tool_call]
        step_call_ids = {getattr(tc, "invocation_id", "") or "" for tc in calls}
        step_call_ids.discard("")
        _tool_invocation_ids.update(step_call_ids)

        # Collect tool results (support both plural tool_results and singular tool_result)
        results: list[Any] = list(step.tool_results) if step.tool_results else []
        if not results and step.tool_result is not None:
            results = [step.tool_result]

        step_has_success = False
        step_has_failure = False
        results_carry_invocation_id = False
        for tr in results:
            inv_id = getattr(tr, "invocation_id", "") or ""
            if inv_id:
                results_carry_invocation_id = True
            if tr.ok:
                if inv_id in step_call_ids:
                    _tool_success_ids.add(inv_id)
                step_has_success = True
                # ok=True 与 error 非空矛盾(fold invariant 该拒绝的样本)
                if tr.error and str(tr.error).strip():
                    tool_ok_error_conflicts.append(step.step_index)
            else:
                step_has_failure = True

        # Legacy journals (and fixtures) write tool_result without an
        # invocation_id; attribute a single-call step's success by its rows.
        if (
            not results_carry_invocation_id
            and len(step_call_ids) == 1
            and any(getattr(tr, "ok", False) for tr in results)
        ):
            _tool_success_ids.add(next(iter(step_call_ids)))

        # Human-in-the-loop (HIL) interaction tools (e.g. askUserQuestion):
        # These tools pause the run to elicit human input rather than returning
        # an in-step EffectReceipt. When the step completed with ok and no error,
        # the interaction question was successfully dispatched and yielded to human.
        for tc in calls:
            inv_id = getattr(tc, "invocation_id", "") or ""
            name = getattr(tc, "name", "") or ""
            if (
                name in ("askUserQuestion", "confirmAction")
                and inv_id
                and step.outcome == "ok"
                and not step.error
            ):
                _tool_success_ids.add(inv_id)
                step_has_success = True

        if step_has_success:
            consecutive = 0
        elif step.outcome == "fail" or (results and step_has_failure):
            failure_steps.append(step.step_index)
            consecutive += 1
            max_consec = max(max_consec, consecutive)
    tool_total = len(_tool_invocation_ids)
    tool_success = len(_tool_success_ids)
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
        tool_ok_error_conflicts=tuple(tool_ok_error_conflicts),
        step_ids=tuple(step_ids),
        step_indexes=tuple(step_indexes),
        tool_invocation_ids=tuple(sorted(_tool_invocation_ids)),
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
