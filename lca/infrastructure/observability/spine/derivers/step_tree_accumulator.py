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
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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


# 闭集 phase EP 表（ADR-0166 D4 闭集）
PHASE_FOLD_EPS: dict[str, StepPhase] = {
    "perceive.phase.fold": "perceive",
    "phase.perceive.fold": "perceive",
    "phase.think.fold": "think",
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
    ) -> None:
        self._run_id = run_id
        self._run_dir = Path(run_dir)
        self._agent_role = agent_role
        self._strategy_key = strategy_key
        self._plan_ref = plan_ref
        self._step_seq = 0
        self._steps: list[JournalStep] = []
        self._phases: list[PhaseRecord] = []
        self._open_step: _StepFrame | None = None
        self._open_segment_id: str | None = None
        self._phase_seq = 0
        self._seg_seq = 0
        self._first_ts: float | None = None
        self._last_ts: float | None = None
        self._objective: str = ""
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
                event.execution_point, exc,
            )

    def flush(self) -> None:
        """收口：把累积状态写 journal.json。

        真实写盘是 cumulative 终态：open step 若仍在，强制 close（fail-safe）。
        """
        try:
            if self._open_step is not None:
                self._close_step("cancelled")
            doc = self._build_document()
            self._last_document = doc
            JournalDocumentWriter(self._run_dir / "journal.json").write(doc)
        except Exception as exc:
            log.warning("step_tree_accumulator.flush failed err=%s", exc)

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

        if ep == "writable.step.start":
            self._begin_step(event, ts)
        elif ep == "writable.step.end":
            self._close_step(outcome=event.outcome or "success")
        elif ep == "writable.segment.start":
            self._begin_segment(event, ts)
        elif ep == "writable.segment.end":
            self._end_segment(outcome=event.outcome or "success")
        elif ep == "phase.perceive.fold":
            self._record_phase(event, "perceive", ts)
        elif ep == "phase.reflect.fold":
            self._record_phase(event, "reflect", ts)
        elif ep == "phase.remember.fold":
            self._record_phase(event, "remember", ts)
        elif ep == "phase.stop.fold":
            self._record_phase(event, "stop", ts)
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
        elif ep == "phase.act.fold.start":
            # 标记当前 step 主相位为 act（override phase）
            if self._open_step is not None:
                self._open_step.phase = "act"
        elif ep == "phase.act.fold.end":
            if self._open_step is not None and not self._open_step.outcome:
                self._open_step.outcome = event.outcome or "ok"

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
            duration_ms=max(0, int((f.exited_at - f.entered_at) * 1000))
            if f.exited_at
            else None,
            context_before=f.context_before,
            thinking=f.thinking,
            tool_call=f.tool_call,
            tool_result=f.tool_result,
            reflect=f.reflect,
            segments=tuple(f.segments),
            outcome=f.outcome,
        )
        self._steps.append(step)
        # 落 model_visible/ 让 replay 可零 token 重建（D3 / D4 ADR-0167）
        self._write_model_visible(f)
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

    def _record_phase(
        self, event: EventRecord, kind: StepPhase, ts: float
    ) -> None:
        self._phase_seq += 1
        ph = PhaseRecord(
            phase_id=f"phase_{self._phase_seq:04d}",
            kind=kind,
            step_id=self._open_step.step_id if self._open_step else None,
            segment_id=self._open_segment_id,
            entered_at=int(ts),
            exited_at=None,
            summary=str(event.payload.get("summary", ""))[:200]
            or None,
            outcome=event.outcome or None,
        )
        self._phases.append(ph)

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
            outcome="completed" if self._steps else "in_progress",
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

    def _write_model_visible(self, frame: _StepFrame) -> None:
        """落 ``model_visible/step_NN/`` 五件套（ADR-0167 D3 / D4）。

        字段：
        - request-header.json  —— { messages_digest, tools_digest, manifest_digest,
                                  run_id, step_id, model, decided_at }
        - system-prompt.md     —— objective + tool inventory 摘要
        - tool-schemas.json    —— 当前可用的工具 schema 列表（空 = 未记录）
        - context-manifest.json—— { kinds, objective, item_count }
        - messages.json        —— 占位骨架 [{role, content, ...}] 供 replay 重建
        """
        import json as _json
        step_dir = self._run_dir / "model_visible" / frame.step_id
        step_dir.mkdir(parents=True, exist_ok=True)

        manifest = {
            "kinds": [k for k in (
                "skill_catalog" if frame.context_before
                and any(getattr(a, "name", "") for a in getattr(frame.context_before, "attachments", ()))
                else None, "objective", "memory"
            ) if k],
            "objective": frame.context_before.objective if frame.context_before else "",
            "item_count": len(getattr(frame.context_before, "attachments", ())) if frame.context_before else 0,
        }
        messages: list[dict[str, Any]] = []
        if frame.context_before is not None:
            messages.append({
                "role": "system",
                "content": frame.context_before.objective,
            })
        if frame.thinking is not None:
            messages.append({
                "role": "assistant",
                "content": frame.thinking.decision or "",
            })
        tool_schemas: list[dict[str, Any]] = []
        if frame.tool_call is not None:
            tool_schemas.append({"name": frame.tool_call.name})
            messages.append({
                "role": "assistant",
                "tool_calls": [{
                    "id": frame.tool_call.invocation_id,
                    "function": {
                        "name": frame.tool_call.name,
                        "arguments": frame.tool_call.arguments,
                    },
                }],
            })
        if frame.tool_result is not None:
            messages.append({
                "role": "tool",
                "content": frame.tool_result.delta_summary or "",
            })

        def _sha(d: Any) -> str:
            return "sha256:" + hashlib.sha256(
                _json.dumps(d, sort_keys=True, ensure_ascii=False, default=str).encode()
            ).hexdigest()

        header = {
            "run_id": self._run_id,
            "step_id": frame.step_id,
            "model": frame.thinking.model if frame.thinking else "unknown",
            "decided_at": frame.entered_at,
            "messages_digest": _sha(messages),
            "tools_digest": _sha(tool_schemas),
            "manifest_digest": _sha(manifest),
        }
        (step_dir / "request-header.json").write_text(
            _json.dumps(header, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        (step_dir / "system-prompt.md").write_text(
            f"# System Prompt — {frame.step_id}\n\n"
            f"objective: {manifest['objective']}\n",
            encoding="utf-8",
        )
        (step_dir / "tool-schemas.json").write_text(
            _json.dumps(tool_schemas, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        (step_dir / "context-manifest.json").write_text(
            _json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        (step_dir / "messages.json").write_text(
            _json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8",
        )

    __all__: list[str] = ["StepTreeAccumulatorDeriver", "PHASE_FOLD_EPS"]
