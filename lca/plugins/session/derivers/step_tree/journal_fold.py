"""fold_step_tree —— 从事件流纯 fold 出 JournalDocument(ADR-0186 PR-3g)。

纯函数集,无 I/O,无 ``logging`` / ``datetime.now`` 等副作用。消费
:class:`EventRecord` 或兼容 ``Mapping`` 形态的事件流,产出
:class:`JournalDocument`(lca.journal/3.1)。

设计原则:

1. **纯 fold** — ``fold_step_tree(events, ...)`` 是一次 left-fold:
   初始空 ``_StepTreeState``,逐 event 左折,最后物化为 ``JournalDocument``。
   与 :class:`StepTreeAccumulatorDeriver` 的 in-memory callback 累积语义
   等价,但不持有 mutable self、不订阅 spine、不写盘。
2. **单一真值表** — ``PHASE_FOLD_EPS`` 复用旧 deriver 闭集,不引入平行词汇。
3. **可测试** — 任何测试 fixture 传 list[dict] 即可驱动 fold,不需要
   SpineReader / EventSpine / 运行中的 run。

生产路径: RunSessionBuilder 装配 StepTreeFoldDeriver,flush 时 fold 本函数。
COMPAT 旧 callback deriver: StepTreeAccumulatorDeriver
(delete-when: rg "StepTreeAccumulatorDeriver(" lca/ = 0 except 其定义文件,
tracking: ADR-0186 PR-3g)。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from lca.contracts.models.observability.journal_doc import (
    JournalDocument,
    JournalMetadata,
)
from lca.contracts.models.observability.journal_step import (
    JournalStep,
    ReflectTrace,
    StepContext,
    ThinkingTrace,
    ToolCallRecord,
    ToolResult,
)
from lca.contracts.models.observability.journal_totals import (
    PhaseRecord,
    SegmentRecord,
    StepPhase,
    Totals,
)

# 闭集 phase EP 表 —— 与 StepTreeAccumulatorDeriver 对齐(ADR-0166 D4 闭集)。
PHASE_FOLD_EPS: dict[str, StepPhase] = {
    "perceive.phase.fold": "perceive",
    "phase.perceive.fold": "perceive",
    "phase.think.fold": "think",
    "phase.act.fold": "act",
    "phase.remember.fold": "remember",
    "phase.reflect.fold": "reflect",
    "phase.stop.fold": "stop",
}


def _epoch_seconds(value: Any) -> float | None:
    """把 when / ts / time 投影成 Unix epoch 秒;无法解析返回 None。"""
    if value is None:
        return None
    if hasattr(value, "timestamp"):
        try:
            return float(value.timestamp())
        except (TypeError, ValueError):
            return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
        # SessionEvent.time 是 epoch 毫秒;spine when 是 epoch 秒。
        if numeric > 1e11:
            return numeric / 1000.0
        return numeric
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
        except ValueError:
            try:
                numeric = float(text)
            except ValueError:
                return None
            if numeric > 1e11:
                return numeric / 1000.0
            return numeric
    return None


def _coerce(event: Any) -> Mapping[str, Any] | None:
    """统一事件形态为 dict-like。

    支持 :class:`EventRecord` / :class:`SpineEventRecord`(属性访问)、
    :class:`SessionEvent` (``type`` + ``data``)、以及 ``Mapping``。
    不识别返回 ``None``,调用方 skip。
    """
    if isinstance(event, Mapping):
        ep = event.get("execution_point")
        if ep:
            return event
        ep = event.get("type") or event.get("category")
        if not ep:
            return event
        payload = event.get("payload") or event.get("data") or {}
        if not isinstance(payload, Mapping):
            payload = {}
        return {
            "execution_point": str(ep),
            "payload": payload,
            "outcome": event.get("outcome") or payload.get("outcome"),
            "phase": event.get("phase", "live"),
            "run_id": event.get("run_id"),
            "when": event.get("when") or event.get("ts") or event.get("time"),
        }
    if hasattr(event, "execution_point") and hasattr(event, "payload"):
        when = getattr(event, "when", None)
        if when is None:
            when = getattr(event, "ts", None)
        return {  # type: ignore[return-value]
            "execution_point": event.execution_point,
            "payload": event.payload if isinstance(event.payload, Mapping) else {},
            "outcome": getattr(event, "outcome", None),
            "phase": getattr(event, "phase", "live"),
            "run_id": getattr(event, "run_id", None),
            "when": when,
        }
    if hasattr(event, "type") and hasattr(event, "data"):
        payload = event.data if isinstance(event.data, Mapping) else {}
        return {
            "execution_point": str(event.type),
            "payload": payload,
            "outcome": payload.get("outcome") if isinstance(payload, Mapping) else None,
            "when": getattr(event, "time", None),
        }
    return None


def _ts(event: Mapping[str, Any]) -> float:
    """从 event 提取 Unix epoch 秒;缺省 0.0。"""
    for key in ("when", "ts", "time"):
        parsed = _epoch_seconds(event.get(key))
        if parsed is not None:
            return parsed
    return 0.0


@dataclass
class _Frame:
    """fold 中间态:一个 step 的累积帧。"""

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


@dataclass
class _StepTreeState:
    """fold 累积器状态(纯数据,无行为)。"""

    step_seq: int = 0
    phase_seq: int = 0
    seg_seq: int = 0
    first_ts: float | None = None
    last_ts: float | None = None
    terminal_outcome: str | None = None
    open_step: _Frame | None = None
    closed_frames: list[_Frame] = field(default_factory=list)
    steps_by_index: dict[int, _Frame] = field(default_factory=dict)
    phases: list[PhaseRecord] = field(default_factory=list)


def _capture_outcome(state: _StepTreeState, ep: str, event: Mapping[str, Any]) -> None:
    """从 terminal EP 捕获 run 终态。"""
    if ep in {"kernel.run.stop", "lifecycle.finally"}:
        ev_outcome = str(event.get("outcome") or "").strip().lower()
        if ev_outcome in {"success", "completed"}:
            state.terminal_outcome = "completed"
        elif ev_outcome in {"fail", "failed", "error"}:
            state.terminal_outcome = "failed"
        elif ev_outcome in {"stop", "stopped", "cancelled", "canceled"}:
            state.terminal_outcome = "stopped"
        elif ev_outcome in {"paused", "waiting_input"}:
            state.terminal_outcome = "paused"
    if ep == "runtime.event_publisher.publish":
        payload = event.get("payload") or {}
        event_type = payload.get("event_type") if isinstance(payload, Mapping) else None
        if event_type == "completed":
            state.terminal_outcome = "completed"
        elif event_type == "failed":
            state.terminal_outcome = "failed"


def _begin_step(state: _StepTreeState, event: Mapping[str, Any], ts: float) -> None:
    if state.open_step is not None:
        _close_step(state, "fail")
    state.step_seq += 1
    payload = event.get("payload") or {}
    phase = payload.get("phase", "think") if isinstance(payload, Mapping) else "think"
    if not isinstance(phase, str):
        phase = "think"
    state.open_step = _Frame(
        step_id=f"step_{state.step_seq:03d}",
        step_index=state.step_seq,
        phase=phase,  # type: ignore[arg-type]
        entered_at=ts,
    )


def _close_step(state: _StepTreeState, outcome: str) -> None:
    if state.open_step is None:
        return
    f = state.open_step
    f.outcome = outcome  # type: ignore[assignment]
    f.exited_at = state.last_ts or f.entered_at
    if f.reflect is None and f.tool_result is not None:
        f.reflect = ReflectTrace(summary=f.tool_result.delta_summary[:200])
    state.open_step = None
    state.closed_frames.append(f)
    state.steps_by_index[f.step_index] = f


def _resolve_target(state: _StepTreeState, payload: Mapping[str, Any]) -> _Frame | None:
    if state.open_step is not None:
        return state.open_step
    event_step_index = payload.get("step_index")
    if isinstance(event_step_index, int):
        for frame in state.closed_frames:
            if frame.step_index == event_step_index:
                return frame
    return None


def _record_phase(
    state: _StepTreeState, kind: StepPhase, ts: float, event: Mapping[str, Any]
) -> None:
    target: _Frame | None = state.open_step
    if target is None and state.closed_frames:
        target = state.closed_frames[-1]
    state.phase_seq += 1
    payload = event.get("payload") or {}
    summary = str(payload.get("summary", ""))[:200] if isinstance(payload, Mapping) else None
    ph = PhaseRecord(
        phase_id=f"phase_{state.phase_seq:04d}",
        kind=kind,
        step_id=target.step_id if target is not None else None,
        entered_at=int(ts),
        summary=summary or None,
        outcome=event.get("outcome"),
    )
    state.phases.append(ph)
    if target is not None and kind in {"think", "act"}:
        state.seg_seq += 1
        target.segments.append(
            SegmentRecord(
                segment_id=f"seg_{state.seg_seq:04d}",
                kind=kind,
                started_at=int(ts),
                outcome=event.get("outcome"),
            )
        )


def _apply(state: _StepTreeState, event: Mapping[str, Any]) -> None:
    """单步 fold:一个 event → state 转换。"""
    ep = str(event.get("execution_point") or "")
    ts = _ts(event)
    state.last_ts = ts
    if state.first_ts is None:
        state.first_ts = ts

    _capture_outcome(state, ep, event)

    payload = event.get("payload") or {}
    if not isinstance(payload, Mapping):
        payload = {}

    if ep == "writable.step.start":
        _begin_step(state, event, ts)
    elif ep == "writable.step.end":
        _close_step(state, str(event.get("outcome") or "success"))
    elif ep in PHASE_FOLD_EPS:
        _record_phase(state, PHASE_FOLD_EPS[ep], ts, event)
    elif ep == "phase.act.fold.start":
        _record_phase(state, "act", ts, event)
    elif ep == "brain.think.start":
        if state.open_step is None:
            state.step_seq += 1
            state.open_step = _Frame(
                step_id=f"step_{state.step_seq:03d}",
                step_index=state.step_seq,
                phase="think",  # type: ignore[arg-type]
                entered_at=ts,
            )
    elif ep == "brain.think.end":
        if state.open_step is not None:
            _close_step(state, str(event.get("outcome") or "success"))
    elif ep == "critic.eval.start":
        _record_phase(state, "reflect", ts, event)
    elif ep == "critic.eval.end":
        _record_phase(state, "reflect", ts, event)
        if state.open_step is not None and state.open_step.phase == "act":
            _close_step(state, str(event.get("outcome") or "success"))
    elif ep == "step.tool_call.record":
        target = _resolve_target(state, payload)
        if target is not None:
            target.tool_call = ToolCallRecord(
                invocation_id=str(payload.get("invocation_id") or ""),
                name=str(payload.get("tool_name") or payload.get("name") or ""),
                arguments=dict(payload["arguments"])
                if isinstance(payload.get("arguments"), dict)
                else {},
                arguments_summary=str(payload.get("arguments_summary") or ""),
            )
    elif ep == "step.tool_result.record":
        target = _resolve_target(state, payload)
        if target is not None:
            files_raw = payload.get("files_created") or ()
            files_tuple = (
                tuple(str(f) for f in files_raw) if isinstance(files_raw, (list, tuple)) else ()
            )
            target.tool_result = ToolResult(
                ok=bool(payload.get("ok", True)),
                latency_ms=int(payload.get("latency_ms") or 0),
                stdout_head=str(payload.get("stdout_head") or "")[:2000],
                stdout_chars_total=int(payload.get("stdout_chars_total") or 0),
                stdout_truncated=bool(payload.get("stdout_truncated") or False),
                stderr=str(payload.get("stderr") or "")[:2000],
                files_created=files_tuple,
                error=payload.get("error"),
                delta_summary=str(payload.get("delta_summary") or ""),
            )
    elif ep == "body.tool.execute.start":
        target = _resolve_target(state, payload)
        if target is not None:
            target.tool_call = ToolCallRecord(
                invocation_id=str(payload.get("invocation_id") or ""),
                name=str(payload.get("tool_name") or payload.get("name") or ""),
                arguments=dict(payload["arguments"])
                if isinstance(payload.get("arguments"), dict)
                else {},
                arguments_summary=str(payload.get("arguments_summary") or ""),
            )
    elif ep == "body.tool.execute.end":
        target = _resolve_target(state, payload)
        if target is not None:
            files_raw = payload.get("files_created") or ()
            files_tuple = (
                tuple(str(f) for f in files_raw) if isinstance(files_raw, (list, tuple)) else ()
            )
            target.tool_result = ToolResult(
                ok=bool(payload.get("ok") or True),
                latency_ms=int(payload.get("latency_ms") or 0),
                stdout_head=str(payload.get("stdout_head") or "")[:2000],
                stdout_chars_total=int(payload.get("stdout_chars_total") or 0),
                stdout_truncated=bool(payload.get("stdout_truncated") or False),
                stderr=str(payload.get("stderr") or "")[:2000],
                files_created=files_tuple,
                error=payload.get("error"),
                delta_summary=str(payload.get("delta_summary") or ""),
            )


def _materialize(
    state: _StepTreeState,
    *,
    run_id: str,
    outcome: str | None = None,
    agent_role: str = "",
    strategy_key: str = "",
    plan_ref: str = "",
    objective: str = "",
) -> JournalDocument:
    """从终态 state 构造 JournalDocument(物化,不修改 state)。"""
    if outcome is not None:
        state.terminal_outcome = outcome
    if state.open_step is not None:
        _close_step(state, "cancelled")
        state.open_step = None

    steps_list = [
        JournalStep(
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
        for f in sorted(state.closed_frames, key=lambda fr: fr.step_index)
    ]

    final_outcome = state.terminal_outcome or ("completed" if state.phases else "in_progress")

    meta = JournalMetadata(
        agent_role=agent_role,
        strategy_key=strategy_key,
        plan_ref=plan_ref,
        objective=objective or "(unobserved)",
        outcome=final_outcome,  # type: ignore[arg-type]
        started_at=state.first_ts or 0.0,
        closed_at=state.last_ts,
        total_steps=len(steps_list),
    )
    seg_count = sum(1 for p in state.phases if p.kind in ("think", "act"))
    return JournalDocument(
        schema="lca.journal/3.1",
        run_id=run_id,
        trace_id=run_id,
        started_at=state.first_ts or 0.0,
        steps=tuple(steps_list),
        metadata=meta,
        closed_at=state.last_ts,
        totals=Totals(steps=len(steps_list), segments=seg_count, phases=len(state.phases)),
        phases=tuple(state.phases),
    )


def fold_step_tree(
    events: Iterable[Any],
    *,
    run_id: str,
    outcome: str | None = None,
    agent_role: str = "",
    strategy_key: str = "",
    plan_ref: str = "",
    objective: str = "",
) -> JournalDocument:
    """纯 fold:从事件流左折出 JournalDocument。

    Parameters:
        events: 可迭代事件(:class:`EventRecord` / :class:`SessionEvent` 或 ``Mapping``)。
            非 fold 目标的事件被 skip(不抛)。
        run_id: 目标 run 标识,写入 document.run_id / trace_id。
        outcome: 显式终态覆盖;None 时由 terminal EP 或启发式推导。
        agent_role / strategy_key / plan_ref / objective: 写入 ``JournalMetadata``。

    Returns:
        JournalDocument(lca.journal/3.1),永远不抛。
    """
    state = _StepTreeState()
    for raw in events:
        coerced = _coerce(raw)
        if coerced is None:
            continue
        try:
            _apply(state, coerced)
        except Exception:  # noqa: S112 — 纯函数不 log;单 event 失败 skip 不中断 fold
            continue
    return _materialize(
        state,
        run_id=run_id,
        outcome=outcome,
        agent_role=agent_role,
        strategy_key=strategy_key,
        plan_ref=plan_ref,
        objective=objective,
    )


__all__ = [
    "PHASE_FOLD_EPS",
    "fold_step_tree",
]
