"""spine-deriver step_tree_accumulator —— 闭 D11 路径（ADR-0167 D11）。

从 spine events 直接累积出 JournalDocument（lca.journal/3.1），最终
由 ``flush()`` 一次性写到 ``journal.json``。 之前 spine → journal 路径
是断的（replay 绕开 spine 直读 journal），本 deriver 是该路径的真正闭合。

设计：
- 单一真理表 ``PHASE_FOLD_EP`` 描述哪些 EP 对应「perceive / think / act」
  三相位 fold（与 ADR-0166 D4 闭集对齐）。
- 工具 / LLM EP 仅做引用累积（不写 tool_call / tool_result 主轨；这两
  个原语由 StepGroupedBackend 在 close_and_finalize 收口）。
- ``flush()`` 把累积状态转 JournalDocument + 写盘。
- **deriver 是纯订阅 + 物化**:不写 model_visible(ADR-0176 D2)。model_visible
  由 :class:`ModelVisibleRecorder` 在 LLM 边界一次性写;deriver 只读
  ``step_id`` 做 phase 累计。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from lca.contracts.models.observability.journal_doc import (
    JournalDocument,
    JournalMetadata,
)
from lca.contracts.models.observability.journal_step import (
    JournalStep,
    ReflectTrace,
    StepContext,
    StepPhase,
    ThinkingTrace,
    ToolCallRecord,
    ToolResult,
)
from lca.contracts.models.observability.journal_totals import (
    PhaseRecord,
    SegmentRecord,
    Totals,
)
from lca.infrastructure.observability.journal.step.projector import (
    JournalDocumentWriter,
)
from lca.infrastructure.observability.spine.derivers.base import Deriver
from lca.infrastructure.observability.spine.event_record import EventRecord

log = logging.getLogger(__name__)


# 闭集 phase EP 表（ADR-0166 D4 闭集 + ADR-0176 D1 扩）
#
# 增补 ADR-0176 D1 §1:
#   - phase.think.fold 必须在 _apply 走 _record_phase 分支(原先表里有但无分支);
#   - phase.act.fold / phase.act.fold.start / phase.act.fold.end 加入
#     PHASE_FOLD_EPS 表(把 act 视作一等 phase fold,不再让 _apply 用硬编码
#     if/elif 来专门覆盖 act.fold.start/end),与 D1 §1 "PHASE_FOLD_EPS 表
#     里有 ≠ _apply 处理了 是已暴露缺陷" 关闭。
# 任何新增 phase.*.fold EP 都应同时落表 + 写 _apply 分支;不增 vocabulary。
PHASE_FOLD_EPS: dict[str, StepPhase] = {
    "perceive.phase.fold": "perceive",
    "phase.perceive.fold": "perceive",
    "phase.think.fold": "think",
    "phase.act.fold": "act",
    "phase.remember.fold": "remember",
    "phase.reflect.fold": "reflect",
    "phase.stop.fold": "stop",
    # writable.* 不视作 phase fold —— 它们定义 step / segment 边
}


@dataclass
class _StepFrame:
    step_id: str
    step_index: int
    phase: StepPhase
    entered_at: float
    context_before: StepContext | None = None
    thinking: ThinkingTrace | None = None
    tool_call: ToolCallRecord | None = None
    tool_result: ToolResult | None = None
    reflect: ReflectTrace | None = None
    segments: list[SegmentRecord] = field(default_factory=list)
    outcome: str | None = None
    exited_at: float | None = None


class StepTreeAccumulatorDeriver(Deriver):
    """从 spine events 累积 JournalDocument（ADR-0167 D11 闭合路径）。

    取代之前 ``spine.deriver.step_tree`` 的 stub 形态；保持 plugin id 不变
    （``spine.deriver.step_tree``）以便 profile / bundle 装配不动。
    """

    def __init__(
        self,
        run_id: str,
        run_dir: Path,
        *,
        agent_role: str = "",
        strategy_key: str = "solo",
        plan_ref: str = "",
        objective: str = "",
    ) -> None:
        self._run_id = run_id
        self._run_dir = Path(run_dir)
        self._agent_role = agent_role
        self._strategy_key = strategy_key
        self._plan_ref = plan_ref
        # objective 在 build 时由 caller 传入(来自 request.user_text);
        # 早先只初始化为空串、运行期从未被赋值,导致 journal.metadata.objective
        # 始终是 "(unobserved)"。同时 spine 上 kernel.run.start.payload 也带
        # objective 作为兜底来源,在 _apply 里二次捕获。
        self._objective: str = objective
        self._step_seq = 0
        self._steps: list[JournalStep] = []
        self._phases: list[PhaseRecord] = []
        self._open_step: _StepFrame | None = None
        self._open_segment_id: str | None = None
        self._phase_seq = 0
        self._seg_seq = 0
        self._first_ts: float | None = None
        self._last_ts: float | None = None
        # terminal outcome 由 materializer.flush(outcome=...) 注入;
        # 同时可从 spine 上 lifecycle.finally / kernel.run.stop 的 outcome 捕获
        self._terminal_outcome: str | None = None
        self._attachments: tuple = ()
        self._last_document: JournalDocument | None = None

    # ── Deriver Protocol ─────────────────────────────────

    def on_event(self, event: EventRecord) -> None:
        if event.run_id != self._run_id:
            return
        if event.phase != "live":
            return
        try:
            self._apply(event)
        except Exception as exc:
            log.warning(
                "step_tree_accumulator on_event failed ep=%s err=%s",
                event.execution_point,
                exc,
            )

    def flush(self, *, outcome: str | None = None) -> None:
        """收口：把累积状态写 journal.json。

        真实写盘是 cumulative 终态：open step 若仍在，强制 close（fail-safe）。

        ``outcome`` 来自 materializer 传入的 RunSession 终态(completed/failed/
        stopped/paused)。早先 flush(outcome=...) 被静默丢弃,_build_document
        永远基于 _steps 是否非空来推断 in_progress/completed,导致 0-step
        但 run 已完成的 journal.json 错误标记 in_progress → doctor H6 误判。
        现优先使用传入的 outcome,没有时回退到 _terminal_outcome(spine
        捕获),再没有才用 _steps 启发式。

        ADR-0176 D1 §1 (3):空写 fail-loud —— 若 ``_open_step is None`` 且
        ``_phases`` 也空,记 ``step_tree_deriver.flush.empty`` structlog.error
        并把诊断写到 ``manifest.extra.flush_errors``;此时仍写 journal.json
        (落一份空 doc),但后续 doctor 走 H-xref broken。
        """
        if outcome is not None:
            self._terminal_outcome = outcome
        try:
            if self._open_step is not None:
                self._close_step("cancelled")
            doc = self._build_document()
            self._last_document = doc
            # ADR-0176 D1 §1 (3):空累积 → fail-loud。
            empty = not self._steps and not self._phases
            if empty:
                try:
                    import structlog

                    _log = structlog.get_logger("lca.observability.step_tree")
                    _log.error(
                        "step_tree_deriver.flush.empty",
                        run_id=self._run_id,
                        terminal_outcome=self._terminal_outcome or "",
                    )
                except Exception as exc:  # pragma: no cover — structlog 不可用兜底
                    log.warning("step_tree flush fail-loud structlog failed err=%s", exc)
                # 把诊断写到 manifest.extra.flush_errors;不在此 assert。
                self._record_flush_error(
                    operation="step_tree.flush.empty",
                    error_message="no step and no phase captured",
                )
            JournalDocumentWriter(self._run_dir / "journal.json").write(doc)
        except Exception as exc:
            log.warning("step_tree_accumulator.flush failed err=%s", exc)

    def _record_flush_error(self, *, operation: str, error_message: str) -> None:
        """ADR-0176 D1 §1 (3):把 flush 期的诊断写进 manifest.extra.flush_errors。

        写到 ``<run_dir>/manifest.json`` 的 ``extra.flush_errors`` 列表(append-only),
        不影响 journal.json 本身。失败由 doctor H-xref hop 读取并报 broken。
        """
        import json

        manifest_path = self._run_dir / "manifest.json"
        payload: dict[str, object] = {}
        if manifest_path.exists():
            try:
                payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                payload = {}
        if not isinstance(payload, dict):
            payload = {}
        extra = payload.get("extra")
        if not isinstance(extra, dict):
            extra = {}
        errors = extra.get("flush_errors")
        if not isinstance(errors, list):
            errors = []
        errors.append(
            {
                "operation": operation,
                "error_message": error_message,
                "ts": self._last_ts or 0.0,
            }
        )
        extra["flush_errors"] = errors
        payload["extra"] = extra
        try:
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
        except Exception as exc:
            log.warning("step_tree_accumulator.record_flush_error failed err=%s", exc)

    @property
    def document(self) -> JournalDocument | None:
        """最后一次 ``flush()`` 的 JournalDocument(供 NarrativeDeriver 读)。

        deriver 不会自发建 document;只在 flush 之后才能拿到。返回 None
        表示还没 flush 过。"""
        return self._last_document

    # ── 累积核心 ──────────────────────────────────────

    def _apply(self, event: EventRecord) -> None:
        ep = event.execution_point
        ts = event.when.timestamp() if event.when else 0.0
        self._last_ts = ts
        if self._first_ts is None:
            self._first_ts = ts

        # Capture run-level terminal outcome from spine; 不依赖 flush() 传入。
        # 优先级低于 materializer.flush(outcome=...) 但作为兜底:即便 caller 漏传,
        # _build_document 也能拿到正确终态。
        if ep in {"kernel.run.stop", "lifecycle.finally"}:
            ev_outcome = (event.outcome or "").strip().lower()
            if ev_outcome in {"success", "completed"}:
                self._terminal_outcome = "completed"
            elif ev_outcome in {"fail", "failed", "error"}:
                self._terminal_outcome = "failed"
            elif ev_outcome in {"stop", "stopped", "cancelled", "canceled"}:
                self._terminal_outcome = "stopped"
            elif ev_outcome in {"paused", "waiting_input"}:
                self._terminal_outcome = "paused"
        # runtime.event_publisher.publish event_type=completed 是更明确的信号
        if ep == "runtime.event_publisher.publish":
            event_type = event.payload.get("event_type")
            if event_type == "completed":
                self._terminal_outcome = "completed"
            elif event_type == "failed":
                self._terminal_outcome = "failed"

        if ep == "writable.step.start":
            self._begin_step(event, ts)
        elif ep == "writable.step.end":
            self._close_step(outcome=event.outcome or "success")
        elif ep == "writable.segment.start":
            self._begin_segment(event, ts)
        elif ep == "writable.segment.end":
            self._end_segment(outcome=event.outcome or "success")
        elif ep in PHASE_FOLD_EPS:
            # ADR-0176 D1 §1:phase fold 统一走 _record_phase;包括 phase.act.fold。
            # 之前 phase.think.fold / phase.act.fold / phase.act.fold.end 表面登记
            # 但 _apply 没有分支 → backend ReAct 路径累积空白,本 ADR 关掉该缺口。
            self._record_phase(event, PHASE_FOLD_EPS[ep], ts)
        elif ep == "phase.act.fold.start":
            # 与 phase.act.fold 同样登记一次 fold(包络 act step 起头)。
            # 这里不直接覆盖 _open_step.phase —— writable.step.start 已经显式
            # 给出 phase,act.fold.start 仅作为冗余 hint 参与 _record_phase 累计。
            self._record_phase(event, "act", ts)
        elif ep == "llm.call.end":
            if self._open_step is not None:
                p = event.payload
                self._open_step.thinking = ThinkingTrace(
                    model=p.get("model", "unknown"),
                    latency_ms=int(p.get("latency_ms") or 0),
                    reasoning="",
                    decision=p.get("decision") or "respond",
                )
        elif ep == "phase.tool.call.start":
            if self._open_step is not None:
                p = event.payload
                self._open_step.tool_call = ToolCallRecord(
                    invocation_id=str(p.get("invocation_id", "")),
                    name=str(p.get("tool_name", "")),
                    arguments={},
                    arguments_summary=str(p.get("arguments_summary", "")),
                )
        elif ep == "phase.tool.call.end":
            if self._open_step is not None:
                p = event.payload
                self._open_step.tool_result = ToolResult(
                    ok=bool(p.get("ok", True)),
                    latency_ms=int(p.get("latency_ms") or 0),
                    delta_summary=str(p.get("delta_summary", "")),
                )
        # ADR-0176 D1 §1 (fallback step 包络,不改 vocabulary):
        # backend ReAct 路径不发 writable.step.*,但发 brain.think.start/end
        # 与 phase.tool.call.* / llm.call.*。在没有显式 step 边界时,
        # 由 brain.think.start 隐式 begin_step("think"),brain.think.end 隐式 close;
        # critic.eval.start/end 主营 reflect 累计,close 已有 open_step=act 时收尾。
        # 显式 > 隐式:writable.step.start/end 永远优先(不变)。
        elif ep == "brain.think.start":
            if self._open_step is None:
                self._begin_implicit_step(event, ts, phase="think")
        elif ep == "brain.think.end":
            if self._open_step is not None:
                # _close_step 内部已幂等:无 open_step 时静默返回;
                # 这里若 begin 来自 writable.step.start 而 end 来自 brain.think.end
                # 不一致 → 仍以 writable.* 为准,_close 仅当 _open_step 存在时落,
                # outcome 取 event.outcome(默认 "success")。
                self._close_step(outcome=event.outcome or "success")
        elif ep == "critic.eval.start":
            # 主营 reflect 累计;若 _open_step 已在 act 上 → 让 _record_phase 落到 reflect
            self._record_phase(event, "reflect", ts)
        elif ep == "critic.eval.end":
            self._record_phase(event, "reflect", ts)
            if self._open_step is not None and self._open_step.phase == "act":
                self._close_step(outcome=event.outcome or "success")
        elif ep == "step.tool_call.record":
            # ADR-0176 D1 §1 (3):fallback 下 open_step 绑 tool_call;
            # 若已由 writable.tool_call.start 写过则覆盖更新。
            if self._open_step is not None:
                p = event.payload.get("call", {}) if isinstance(event.payload, dict) else {}
                self._open_step.tool_call = ToolCallRecord(
                    invocation_id=str(p.get("invocation_id", "")),
                    name=str(p.get("name", "")),
                    arguments=p.get("arguments") or {},
                    arguments_summary=str(p.get("arguments_summary", "")),
                )
        elif ep == "step.tool_result.record":
            if self._open_step is not None:
                p = event.payload.get("result", {}) if isinstance(event.payload, dict) else {}
                self._open_step.tool_result = ToolResult(
                    ok=bool(p.get("ok", True)),
                    latency_ms=int(p.get("latency_ms") or 0),
                    delta_summary=str(p.get("delta_summary", "")),
                )
        elif ep == "body.tool.execute.start":
            # backend ReAct 把 tool_call 落到该 EP;有 open_step 时一并 bind。
            if self._open_step is not None:
                p = event.payload
                self._open_step.tool_call = ToolCallRecord(
                    invocation_id=str(p.get("invocation_id", "")),
                    name=str(p.get("tool_name", p.get("name", ""))),
                    arguments=p.get("arguments") or {},
                    arguments_summary=str(p.get("arguments_summary", "")),
                )
        elif ep == "body.tool.execute.end" and self._open_step is not None:
            p = event.payload
            self._open_step.tool_result = ToolResult(
                ok=bool(p.get("ok", True)),
                latency_ms=int(p.get("latency_ms") or 0),
                delta_summary=str(p.get("delta_summary", "")),
                )

    def _begin_step(self, event: EventRecord, ts: float) -> None:
        if self._open_step is not None:
            # 嵌套 begin_step 视为上一 step 收口失败 → 强制 close
            self._close_step("fail")
        self._step_seq += 1
        phase = event.payload.get("phase", "think")
        if not isinstance(phase, str):
            phase = "think"
        self._open_step = _StepFrame(
            step_id=f"step_{self._step_seq:03d}",
            step_index=self._step_seq,
            phase=phase,  # type: ignore[arg-type]
            entered_at=ts,
            context_before=StepContext(objective=self._objective),
        )

    def _begin_implicit_step(self, event: EventRecord, ts: float, *, phase: str) -> None:
        """ADR-0176 D1 §1 (2):fallback step 包络。

        backend ReAct 路径不显式发 writable.step.start;当收到
        ``brain.think.start`` 且无 _open_step 时,隐式 begin_step。
        ``phase`` 默认 "think";critic.eval.start 走 _record_phase 累计 reflect,
        不在此 begin step。
        """
        if self._open_step is not None:
            # 已有显式 step(来自 writable.step.start 或上轮 brain.think.start)
            # → 不嵌套;复用现有 _open_step(包络优先级:显式 > 隐式)。
            return
        self._step_seq += 1
        self._open_step = _StepFrame(
            step_id=f"step_{self._step_seq:03d}",
            step_index=self._step_seq,
            phase=phase,  # type: ignore[arg-type]
            entered_at=ts,
            context_before=StepContext(objective=self._objective),
        )

    def _close_step(self, outcome: str) -> None:
        if self._open_step is None:
            return
        f = self._open_step
        f.outcome = outcome  # type: ignore[assignment]
        f.exited_at = self._last_ts or f.entered_at
        # reflect 默认摘要
        if f.reflect is None and f.tool_result is not None:
            f.reflect = ReflectTrace(summary=f.tool_result.delta_summary[:200])
        # construct JournalStep
        step = JournalStep(
            step_id=f.step_id,
            step_index=f.step_index,
            phase=f.phase,
            entered_at=f.entered_at,
            exited_at=f.exited_at,
            duration_ms=max(0, int((f.exited_at - f.entered_at) * 1000)) if f.exited_at else None,
            context_before=f.context_before,
            thinking=f.thinking,
            tool_call=f.tool_call,
            tool_result=f.tool_result,
            reflect=f.reflect,
            segments=tuple(f.segments),
            outcome=f.outcome,
        )
        self._steps.append(step)
        # ADR-0176 D2:deriver 是纯订阅 + 物化,不再落 model_visible。
        # model_visible 由 ModelVisibleRecorder 在 LLM 边界一次性写。
        self._open_step = None

    def _begin_segment(self, event: EventRecord, ts: float) -> None:
        if self._open_step is None:
            return
        self._seg_seq += 1
        seg_id = f"seg_{self._seg_seq:04d}"
        seg_kind = str(event.payload.get("kind", "think"))
        seg = SegmentRecord(
            segment_id=seg_id,
            kind=seg_kind,
            started_at=int(ts),
        )
        self._open_step.segments.append(seg)
        self._open_segment_id = seg_id

    def _end_segment(self, outcome: str) -> None:
        if self._open_segment_id is None or self._open_step is None:
            return
        # SegmentRecord is frozen — replace the last segment via dataclasses.replace.
        from dataclasses import replace as _dc_replace

        old = self._open_step.segments[-1]
        try:
            ended_at = int(self._last_ts or 0)
        except (TypeError, ValueError):
            ended_at = 0
        new_seg = _dc_replace(old, ended_at=ended_at, outcome=outcome)
        self._open_step.segments[-1] = new_seg
        self._open_segment_id = None

    def _record_phase(self, event: EventRecord, kind: StepPhase, ts: float) -> None:
        self._phase_seq += 1
        ph = PhaseRecord(
            phase_id=f"phase_{self._phase_seq:04d}",
            kind=kind,
            step_id=self._open_step.step_id if self._open_step else None,
            segment_id=self._open_segment_id,
            entered_at=int(ts),
            exited_at=None,
            summary=str(event.payload.get("summary", ""))[:200] or None,
            outcome=event.outcome or None,
        )
        self._phases.append(ph)
        # ADR-0176 D1 §1 (2):phase.fold(think / act)累计到当前 _open_step.segments
        # —— 替代旧实现「只在 writable.segment.* 累计」造成的 backend ReAct 路径
        # segments 永远空的缺陷。segs 只用于人读叙事聚合,不参与 _resolve_outcome。
        if self._open_step is not None and kind in {"think", "act"}:
            self._seg_seq += 1
            self._open_step.segments.append(
                SegmentRecord(
                    segment_id=f"seg_{self._seg_seq:04d}",
                    kind=kind,
                    started_at=int(ts),
                    ended_at=None,
                    outcome=event.outcome,
                )
            )

    def _build_document(self) -> JournalDocument:
        seg_count = sum(1 for p in self._phases if p.kind in ("think", "act"))
        totals = Totals(
            steps=len(self._steps),
            segments=seg_count,
            phases=len(self._phases),
        )
        meta = JournalMetadata(
            agent_role=self._agent_role,
            strategy_key=self._strategy_key,
            plan_ref=self._plan_ref,
            objective=self._objective or "(unobserved)",
            # outcome 三路优先级:
            # 1) materializer.flush(outcome=...) 注入(self._terminal_outcome)
            # 2) spine 上的 terminal 事件(kernel.run.stop / lifecycle.finally /
            #    runtime.event_publisher.publish event_type=completed)
            # 3) 兜底:有 step → completed;否则 in_progress(旧启发式)
            outcome=self._resolve_outcome(),
            started_at=self._first_ts or 0.0,
            closed_at=self._last_ts,
            total_steps=len(self._steps),
        )
        return JournalDocument(
            schema="lca.journal/3.1",
            run_id=self._run_id,
            trace_id=self._run_id,
            started_at=self._first_ts or 0.0,
            steps=tuple(self._steps),
            metadata=meta,
            closed_at=self._last_ts,
            totals=totals,
            phases=tuple(self._phases),
        )

    def _resolve_outcome(self) -> str:
        """决定 JournalMetadata.outcome。

        优先级:
          1) self._terminal_outcome —— materializer.flush(outcome=...) 或 spine
             捕获的 kernel.run.stop / lifecycle.finally / event_publisher.publish。
          2) ``closed_at`` 已被 set + 有任何 phases/steps → completed
             (model-only respond 没 step 也有 phases)。
          3) 兜底:有 step → completed;否则 in_progress(旧启发式)。
        """
        if self._terminal_outcome:
            return self._terminal_outcome
        if self._last_ts is not None and (self._steps or self._phases):
            return "completed"
        return "completed" if self._steps else "in_progress"

    __all__: list[str] = ["StepTreeAccumulatorDeriver", "PHASE_FOLD_EPS"]  # noqa: RUF012
