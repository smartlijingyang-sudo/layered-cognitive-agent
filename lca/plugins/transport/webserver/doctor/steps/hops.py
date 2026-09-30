"""Doctor.v3 hop 判定函数(H1..H8 / H-seg / H-phase / H-xref / H-ssot / H-mv-journal / H-fold)。

每个 ``_hop_*`` 接收 ``StepScan``(或 ``mode``)并返回 :class:`HopVerdict`;
判定语义与 ADR-0164 / ADR-0176 / ADR-0185 / ADR-0244 一一对应。
``_summary`` 生成 DoctorReport.summary 单行文本。
"""

from __future__ import annotations

from typing import Any

from lca.infrastructure.observability.replay.fold_source import SOURCE_FOLD
from lca.plugins.transport.webserver.doctor.models import (
    DoctorMode,
    HopVerdict,
    StepScan,
)


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
    """step_id 唯一 + step_index 顺序 1..N 连续无跳号。

    COMPAT(owner: PR-B H3, from: stub-ok-True, to: real duplicate/continuity check,
           delete_when: scan.step_ids 与 scan.step_indexes 不再有空 tuple 回退,
           forbidden_new_usage: 新 journal schema 不得允许重复 step_id)。
    """
    if not scan.exists:
        return HopVerdict(ok=None, detail="not evaluated")
    extra: dict[str, Any] = {
        "total_steps": scan.total_steps,
        "step_ids": list(scan.step_ids),
        "step_indexes": list(scan.step_indexes),
    }
    # 1. duplicate step_id
    seen_ids: dict[str, int] = {}
    for sid in scan.step_ids:
        seen_ids[sid] = seen_ids.get(sid, 0) + 1
    dup_ids = [sid for sid, cnt in seen_ids.items() if cnt > 1]
    if dup_ids:
        extra["duplicate_step_ids"] = dup_ids
        return HopVerdict(
            ok=False,
            detail=f"duplicate step_id: {dup_ids}",
            extra=extra,
        )
    # 2. step_index continuity: must equal list(range(1, N+1))
    indexes = list(scan.step_indexes)
    expected = list(range(1, len(indexes) + 1))
    if indexes != expected:
        return HopVerdict(
            ok=False,
            detail=f"step_index 不连续: 实际 {indexes}, 期望 {expected}",
            extra=extra,
        )
    return HopVerdict(ok=True, detail=f"{scan.total_steps} steps 顺序闭合", extra=extra)


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
    # 回归锁 run_1f5360d2fa47:fold invariant 应在生产路径上抛
    # FoldConsistencyError;残留 journal 文件可能含历史矛盾样本,
    # doctor 必须显式识别。
    if scan.tool_ok_error_conflicts:
        return HopVerdict(
            ok=False,
            detail=(
                f"工具结果矛盾 step(s)={list(scan.tool_ok_error_conflicts)} "
                f"(ok=True 但 error 非空 — fold invariant 已被上游触发或绕过)"
            ),
            extra={
                **extra,
                "tool_ok_error_conflicts": list(scan.tool_ok_error_conflicts),
            },
        )
    # H7 多源对账:spine phase.tool.call.end.ok 与 journal step.tool_result.ok
    # 互相对账。不一致即 H7.ok=False。
    if scan.spine_phase_tool_call_end_total > 0:
        spine_total = scan.spine_phase_tool_call_end_total
        extra["spine_phase_tool_call_end_total"] = spine_total
        extra["journal_tool_total"] = scan.tool_total

        # ADR-0244 PR-1 Task 3: 精准集合对账
        journal_invs = set(scan.tool_invocation_ids)
        spine_invs = set(scan.spine_tool_invocation_ids)
        missing_in_journal = sorted(spine_invs - journal_invs) if spine_invs else []
        missing_in_spine = sorted(journal_invs - spine_invs) if spine_invs else []
        if missing_in_journal:
            extra["missing_in_journal"] = missing_in_journal
        if missing_in_spine:
            extra["missing_in_spine"] = missing_in_spine

        # PR-D: parity check — journal distinct invocation count must match
        # spine phase.tool.call.end total.
        if scan.tool_total != spine_total:
            # ADR-0244: the total_steps == tool_total < spine_total heuristic is
            # retired. Forked detection is only valid when spine events carry step
            # info; otherwise the set differences are the precise verdict.
            if scan.spine_tool_has_step_info:
                forked = scan.spine_tool_forked
                extra["forked_tool_calls"] = forked
                detail = (
                    f"H7 step-tree 每步只投影一个 tool_call,本 run 有并发工具调用 "
                    f"({scan.tool_total} steps 承载 {spine_total} 次调用);"
                    f"事实层 step.tool_call.record 完整"
                    if forked
                    else (
                        f"H7 journal/spine tool_total mismatch ({scan.tool_total} vs {spine_total})"
                        + (
                            f": missing in journal {missing_in_journal}"
                            if missing_in_journal
                            else ""
                        )
                        + (f": missing in spine {missing_in_spine}" if missing_in_spine else "")
                    )
                )
                return HopVerdict(
                    ok=None if forked else False,
                    detail=detail,
                    extra=extra,
                )
            detail = (
                f"H7 journal/spine tool_total mismatch ({scan.tool_total} vs {spine_total})"
                + (f": missing in journal {missing_in_journal}" if missing_in_journal else "")
                + (f": missing in spine {missing_in_spine}" if missing_in_spine else "")
            )
            return HopVerdict(ok=False, detail=detail, extra=extra)
        spine_fail = scan.spine_phase_tool_call_end_failure_count
        journal_fail = scan.tool_total - scan.tool_success
        if spine_fail > 0 and journal_fail == 0:
            return HopVerdict(
                ok=False,
                detail=(
                    f"journal↔spine inconsistency: spine 报 {spine_fail}/{spine_total} 失败, "
                    f"但 journal 报 0 失败(失真源在 step.tool_result.record)"
                ),
                extra={
                    **extra,
                    "spine_phase_tool_call_end_total": spine_total,
                    "spine_phase_tool_call_end_failure_count": spine_fail,
                    "journal_tool_total": scan.tool_total,
                    "journal_tool_success": scan.tool_success,
                },
            )
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
