"""fold_step_tree —— 从事件流纯 fold 出 JournalDocument(ADR-0186 PR-3g)。

纯函数集,无 I/O,无 ``logging`` / ``datetime.now`` 等副作用。消费两路
事件流,产出 :class:`JournalDocument`(lca.journal/3.1):

- **spine 形态** —— ``execution_point`` 属性 / ``execution_point`` mapping
  key 携带裸 EP(:class:`EventRecord`、``SpineReader.read_dicts()`` dict)。
- **Session 形态** —— ``type`` + ``data`` 信封(:class:`SessionEvent` 或
  同形 Mapping);``type`` 是 spine CATEGORY 前缀串(例
  ``spine.cognition.brain.think.start``),经
  :func:`~lca_kernel.events.payloads_spine.category_to_spine_ep`
  反查归一为裸 EP,未登记的 type 原样透传。

Step 边界语法(闭集,不引入新词表):

- ``writable.step.start`` / ``writable.step.end`` —— 显式 step 边。
- ``llm.request.header`` —— cursor step 边(StdLoopCursor.record_request_header):
  已开 step 以 ``success`` 关闭;新 step 以 payload ``step_id`` 开启,
  缺省 ``step_{seq:03d}``;payload ``model`` / ``reason`` 留在帧上。
- ``brain.think.start`` / ``brain.think.end`` —— 无显式边时的隐式 think step。
- ``phase.*.fold``(:data:`PHASE_FOLD_EPS`)—— phase 累计,不切 step。

设计原则:

1. **纯 fold** — ``fold_step_tree(events, ...)`` 是一次 left-fold:
   初始空 ``_StepTreeState``,逐 event 左折,最后物化为 ``JournalDocument``。
   不持有 mutable self、不订阅 spine、不写盘 —— 写盘由
   :class:`StepTreeFoldDeriver` (ADR-0212 §5 fail-loud) 负责,
   失败抛 :class:`JournalWriteError`,不 swallow。
2. **单一真值表** — ``PHASE_FOLD_EPS`` 闭集(ADR-0166 D4),不引入平行词汇。
   run 终态同理只有一个权威:``kernel.run.stop``(唯一 producer
   :func:`lca.loop.transport.emit_kernel_run_stop`),其余 terminal EP 只是
   证据,不得覆盖它(见 :data:`_RUN_OUTCOME_AUTHORITY`)。
3. **可测试** — 任何测试 fixture 传 list[dict] 即可驱动 fold,不需要
   SpineReader / EventSpine / 运行中的 run。

生产路径: RunSessionBuilder 装配 StepTreeFoldDeriver,flush 时 fold 本函数
（I-SESSION-5）。本模块是 journal.json 派生面的唯一真值函数（ADR-0212）。
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, cast

from lca.contracts.atoms.ids.ids import RunId, TraceId
from lca.contracts.models.observability.journal.doc import (
    JournalDocument,
    JournalMetadata,
)
from lca.contracts.models.observability.journal.step import (
    JournalStep,
    ReflectTrace,
    StepContext,
    StepOutcome,
    ThinkingTrace,
    ToolCallRecord,
    ToolResult,
)
from lca.contracts.models.observability.journal.totals import (
    PhaseRecord,
    SegmentRecord,
    StepPhase,
    Totals,
)
from lca_kernel.events.fold.binding_engine import JournalBindingEngine, header_model_from_payload
from lca_kernel.events.payloads.spine import category_to_spine_ep

# 闭集 phase EP 表 —— ADR-0166 D4 闭集；ADR-0212 后为 fold 唯一真值表。
PHASE_FOLD_EPS: dict[str, StepPhase] = {
    "perceive.phase.fold": "perceive",
    "phase.perceive.fold": "perceive",
    "phase.think.fold": "think",
    "phase.act.fold": "act",
    "phase.remember.fold": "remember",
    "phase.reflect.fold": "reflect",
    "phase.stop.fold": "stop",
}

_BINDING_ENGINE: JournalBindingEngine | None = None


def _binding_engine() -> JournalBindingEngine:
    global _BINDING_ENGINE
    if _BINDING_ENGINE is None:
        _BINDING_ENGINE = JournalBindingEngine()
    return _BINDING_ENGINE


def reset_journal_binding_engine() -> None:
    """Test seam: drop cached binding engine (after plan cache reset)."""
    global _BINDING_ENGINE
    _BINDING_ENGINE = None


def _resolve_execution_point(name: str) -> str:
    """spine CATEGORY 前缀串 → 裸 EP;未登记的 type 原样返回。

    反查真值在 :func:`lca_kernel.events.payloads_spine.category_to_spine_ep`
    (Session 形态事件的 ``type`` 是 spine CATEGORY 前缀串,例
    ``spine.cognition.brain.think.start``;fold 语法按裸 EP 匹配)。
    """
    return category_to_spine_ep(name) or name


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
    spine 形态(``execution_point`` key / 属性)已是裸 EP,原样透传;
    Session 形态(``type`` / ``category`` key、``type`` 属性)的 category
    前缀串经 :func:`_resolve_execution_point` 反查为裸 EP,未登记的原样透传。
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
            "execution_point": _resolve_execution_point(str(ep)),
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
        return {
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
            "execution_point": _resolve_execution_point(str(event.type)),
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


def _truncate_kept(text: str, *, head: int, tail: int) -> str:
    """Truncate ``text`` to at most ``head + tail + 12`` characters.

    中间折叠为 ``"\\n… [truncated N chars] …\\n"``。全文在
    ``<run_id>.spine.jsonl``(``llm.stream.token`` 事件 SSOT;ADR-0185),
    这里只是 viewport 投影。
    """
    if not text:
        return ""
    total = len(text)
    if total <= head + tail + 64:
        return text
    head_part = text[:head]
    tail_part = text[-tail:] if tail else ""
    middle_dropped = total - head - tail
    return f"{head_part}\n… [{middle_dropped} chars truncated] …\n{tail_part}"


def _journal_step_outcome(raw: str | None) -> StepOutcome | None:
    """Map fold/runtime outcome strings onto journal ``StepOutcome`` literals."""
    if raw is None:
        return None
    normalized = raw.strip().lower()
    if normalized in {"success", "completed", "ok", ""}:
        return "ok"
    if normalized in {"fail", "failed", "error"}:
        return "fail"
    if normalized in {"skip", "skipped", "cancelled", "canceled", "stopped"}:
        return "skip"
    return cast("StepOutcome", normalized)


@dataclass
class _Frame:
    """fold 中间态:一个 step 的累积帧。

    step 边界由 ``llm.request.header`` EP 唯一驱动(SSOT)。其他 EP 按
    顺序挂到当前 open 帧上,不参与切步。

    ``model`` / ``request_reason`` 由 ``llm.request.header`` payload 写入;
    ``step.thinking.record`` 构造 ThinkingTrace 时从 ``model`` 取模型名。

    ``llm_started`` / ``stream_*_chunks``:Session 形态的 ``llm.stream.token``
    按 ``channel_kind`` 分流累积(reasoning vs output);``llm.call.end``
    收口时拼成 ThinkingTrace。ADR-0212 收口后,fold 是 journal step
    帧累积的唯一真值路径。
    """

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
    error: str | None = None
    exited_at: float | None = None
    model: str = ""
    request_reason: str = ""
    llm_started: bool = False
    stream_reasoning_chunks: list[str] = field(default_factory=list)
    stream_final_chunks: list[str] = field(default_factory=list)


@dataclass
class _StepTreeState:
    """fold 累积器状态(纯数据,无行为)。"""

    step_seq: int = 0
    phase_seq: int = 0
    seg_seq: int = 0
    first_ts: float | None = None
    last_ts: float | None = None
    terminal_outcome: str | None = None
    terminal_outcome_rank: int = 0
    open_step: _Frame | None = None
    closed_frames: list[_Frame] = field(default_factory=list)
    phases: list[PhaseRecord] = field(default_factory=list)


# run 终态两级权威。kernel.run.stop 是唯一 run-outcome producer
# (lca.loop.transport.emit_kernel_run_stop);其余 terminal EP 只是证据。
# 证据不覆盖权威,权威也不靠到达顺序取胜(recovery spine 可含多份)。
_RUN_OUTCOME_AUTHORITY = 2
_RUN_OUTCOME_EVIDENCE = 1

# producer 词表只有 success / failure / cancelled(现场 spine 实测无第四种)。
# 词表外一律 failed:同 EP 的 LifecycleDeriver 也把 non-success 判 failed,
# 而 fold 契约「永不抛」会让 raise 被 _apply 的 swallow 吃掉 —— 只有悲观
# 映射不会静默放过。
_KERNEL_RUN_STOP_OUTCOMES: dict[str, str] = {"success": "completed", "cancelled": "stopped"}


def _event_outcome(event: Mapping[str, Any]) -> str:
    """读事件 outcome 词:spine 记录放在 payload 里,EventRecord 放在顶层。"""
    raw = event.get("outcome")
    if not raw:
        payload = event.get("payload")
        if isinstance(payload, Mapping):
            raw = payload.get("outcome")
    return str(raw or "").strip().lower()


def _stamp_terminal(state: _StepTreeState, outcome: str, rank: int) -> None:
    """写 run 终态;低 rank 不得覆盖高 rank,同 rank last-write-wins。"""
    if rank < state.terminal_outcome_rank:
        return
    state.terminal_outcome = outcome
    state.terminal_outcome_rank = rank


def _capture_outcome(state: _StepTreeState, ep: str, event: Mapping[str, Any]) -> None:
    """从 terminal EP 捕获 run 终态。"""
    if ep == "exception.caught":
        _stamp_terminal(state, "failed", _RUN_OUTCOME_EVIDENCE)
        return
    if ep == "kernel.run.stop":
        outcome = _KERNEL_RUN_STOP_OUTCOMES.get(_event_outcome(event), "failed")
        _stamp_terminal(state, outcome, _RUN_OUTCOME_AUTHORITY)
        return
    if ep == "runtime.event_publisher.publish":
        payload = event.get("payload") or {}
        event_type = payload.get("event_type") if isinstance(payload, Mapping) else None
        if event_type == "completed":
            _stamp_terminal(state, "completed", _RUN_OUTCOME_EVIDENCE)
        elif event_type == "failed":
            _stamp_terminal(state, "failed", _RUN_OUTCOME_EVIDENCE)


def _open_step(
    state: _StepTreeState, step_id: str, model: str, request_reason: str, ts: float
) -> _Frame:
    """step 边界单一入口(SSOT):``llm.request.header`` 触发。

    每次 LLM 边界 = 一步:关旧帧(若开)→ 开新帧。step_id 直接来自
    payload(cursor / hook 单派生,不再需要 fold 端"原地升级"合并)。
    不读 payload.phase:phase 由 phase.fold 唯一决定。
    """
    if state.open_step is not None:
        _close_step(state, "success")
    state.step_seq += 1
    frame = _Frame(
        step_id=step_id,
        step_index=state.step_seq,
        phase="think",
        entered_at=ts,
        model=model,
        request_reason=request_reason,
    )
    state.open_step = frame
    return frame


def _tool_result_ok(payload: Mapping[str, Any]) -> bool:
    """从 tool result / body.tool.execute.end payload 推导 ok。"""
    if "ok" in payload:
        return bool(payload.get("ok"))
    outcome = str(payload.get("outcome") or "success").strip().lower()
    return outcome in {"success", "completed", "ok", ""}


def _assign_tool_call(target: _Frame, payload: Mapping[str, Any], ep: str) -> None:
    # 不同 invocation_id = 不同 tool,新帧覆盖;同 invocation_id = 同一 tool
    # 的镜像 record,走 binding merge 累积字段(避免 listFiles → readFile
    # 互相覆盖的回归:run_3cf06424f0b7)。
    incoming_inv = str(payload.get("invocation_id") or "")
    existing_inv = (
        str(getattr(target.tool_call, "invocation_id", "") or "")
        if target.tool_call is not None
        else ""
    )
    if incoming_inv and existing_inv and incoming_inv != existing_inv:
        target.tool_call = _binding_engine().apply_tool_call(None, payload, ep)
    else:
        target.tool_call = _binding_engine().apply_tool_call(target.tool_call, payload, ep)


def _assign_tool_result(target: _Frame, payload: Mapping[str, Any], ep: str) -> None:
    incoming_inv = str(payload.get("invocation_id") or "")
    existing_inv = (
        str(getattr(target.tool_result, "invocation_id", "") or "")
        if target.tool_result is not None
        else ""
    )
    if incoming_inv and existing_inv and incoming_inv != existing_inv:
        target.tool_result = _binding_engine().apply_tool_result(
            None, payload, ep, ok_default=_tool_result_ok(payload)
        )
    else:
        target.tool_result = _binding_engine().apply_tool_result(
            target.tool_result,
            payload,
            ep,
            ok_default=_tool_result_ok(payload),
        )


def _capture_exception(state: _StepTreeState, payload: Mapping[str, Any], ts: float) -> None:
    """``exception.caught`` → 关联 step 错误 + run 终态 failed。"""
    _stamp_terminal(state, "failed", _RUN_OUTCOME_EVIDENCE)
    msg = str(payload.get("exception_message") or payload.get("reason") or "").strip()
    if not msg:
        exc_type = str(payload.get("exception_class") or payload.get("exc_type") or "Error")
        msg = exc_type
    target = state.open_step
    if target is None and state.closed_frames:
        target = state.closed_frames[-1]
    if target is not None:
        target.error = msg[:2000]
        target.outcome = "failed"
        if target.exited_at is None:
            target.exited_at = ts


def _close_step(state: _StepTreeState, outcome: str) -> None:
    if state.open_step is None:
        return
    f = state.open_step
    f.outcome = outcome
    f.exited_at = state.last_ts or f.entered_at
    if f.reflect is None and f.tool_result is not None:
        f.reflect = ReflectTrace(summary=f.tool_result.delta_summary[:200])
    state.open_step = None
    state.closed_frames.append(f)


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

    # step 边界单一信号:llm.request.header(SSOT)。其他 EP 挂到当前帧。
    if ep == "llm.request.header":
        header_step_id = str(payload.get("step_id") or "")
        header_model = header_model_from_payload(payload) or str(payload.get("model") or "")
        if not header_step_id:
            # 缺 step_id 时退化:取 cursor 当前 step_index + 1;
            # 正常路径 hook 必带 step_id,缺值即 fold 抛错更安全。
            return
        frame = _open_step(
            state,
            step_id=header_step_id,
            model=header_model,
            request_reason=str(payload.get("reason") or ""),
            ts=ts,
        )
        frame.thinking = _binding_engine().apply_thinking_patch(
            frame.thinking,
            payload,
            ep,
            frame_model=header_model,
        )
    elif ep == "llm.call.start":
        # 标记 LLM 窗口开启;stream.token 据此判断是否属于当前 step。
        if state.open_step is not None:
            state.open_step.llm_started = True
            call_model = str(payload.get("model") or "")
            if call_model and not state.open_step.model:
                state.open_step.model = call_model
    elif ep == "llm.stream.token":
        # Session 形态:按 channel_kind 分流累积 reasoning / output。
        target = state.open_step
        if target is not None and target.llm_started:
            delta = str(payload.get("text_delta") or "")
            if delta:
                kind = payload.get("channel_kind") or "output"
                if kind == "reasoning":
                    target.stream_reasoning_chunks.append(delta)
                else:
                    target.stream_final_chunks.append(delta)
    elif ep == "llm.call.end":
        # 收口:把累积的 stream 缓冲拼成 ThinkingTrace。
        target = state.open_step
        if target is not None:
            model = str(payload.get("model") or target.model or "unknown")
            latency_ms = int(payload.get("latency_ms") or 0)
            prompt_tokens = payload.get("prompt_tokens")
            completion_tokens = payload.get("completion_tokens")
            reasoning_text = "".join(target.stream_reasoning_chunks)
            final_text = "".join(target.stream_final_chunks)
            reasoning_kept = _truncate_kept(reasoning_text, head=2048, tail=1024)
            final_kept = _truncate_kept(final_text, head=4096, tail=1024)
            target.thinking = ThinkingTrace(
                model=model,
                latency_ms=latency_ms,
                reasoning=reasoning_kept,
                prompt_tokens=int(prompt_tokens)
                if isinstance(prompt_tokens, (int, float))
                else None,
                completion_tokens=int(completion_tokens)
                if isinstance(completion_tokens, (int, float))
                else None,
                raw_response_preview=final_kept[:600] if final_kept else "",
            )
            target.llm_started = False
            target.stream_reasoning_chunks.clear()
            target.stream_final_chunks.clear()
    elif ep == "llm.request.header.assistant":
        # 模型所见即日志:assistant message 是 LLM 响应的 SSOT。
        target = state.open_step
        if target is not None:
            assistant_content = str(payload.get("assistant_content") or "")
            tool_calls = payload.get("tool_calls")
            usage_raw = payload.get("usage")
            usage: dict[str, Any] = dict(usage_raw) if isinstance(usage_raw, Mapping) else {}
            if target.thinking is not None:
                thinking = target.thinking
                prompt_tokens = thinking.prompt_tokens
                if prompt_tokens is None:
                    pt = usage.get("prompt_tokens")
                    if isinstance(pt, (int, float)):
                        prompt_tokens = int(pt)
                completion_tokens = thinking.completion_tokens
                if completion_tokens is None:
                    ct = usage.get("completion_tokens")
                    if isinstance(ct, (int, float)):
                        completion_tokens = int(ct)
                target.thinking = replace(
                    thinking,
                    raw_response_preview=assistant_content[:600]
                    if assistant_content
                    else thinking.raw_response_preview,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    decision="use_tool"
                    if isinstance(tool_calls, list) and tool_calls
                    else ("respond" if assistant_content.strip() else thinking.decision),
                )
            else:
                prompt_tokens_raw = usage.get("prompt_tokens")
                completion_tokens_raw = usage.get("completion_tokens")
                target.thinking = ThinkingTrace(
                    model=target.model or "unknown",
                    latency_ms=0,
                    reasoning="",
                    decision="use_tool"
                    if isinstance(tool_calls, list) and tool_calls
                    else ("respond" if assistant_content.strip() else ""),
                    prompt_tokens=int(prompt_tokens_raw)
                    if isinstance(prompt_tokens_raw, (int, float))
                    else None,
                    completion_tokens=int(completion_tokens_raw)
                    if isinstance(completion_tokens_raw, (int, float))
                    else None,
                    raw_response_preview=assistant_content[:600] if assistant_content else "",
                )
            if isinstance(tool_calls, list) and tool_calls:
                first_call = tool_calls[0]
                if isinstance(first_call, Mapping):
                    call_args = first_call.get("arguments") or first_call.get("args") or {}
                    fn = first_call.get("function")
                    if isinstance(fn, Mapping):
                        name = str(fn.get("name") or "")
                        if not call_args:
                            raw_args = fn.get("arguments") or ""
                            if isinstance(raw_args, str) and raw_args:
                                try:
                                    call_args = json.loads(raw_args)
                                except (json.JSONDecodeError, ValueError):
                                    call_args = {}
                    else:
                        name = str(first_call.get("name") or "")
                    target.tool_call = ToolCallRecord(
                        invocation_id=str(
                            first_call.get("id") or first_call.get("invocation_id") or ""
                        ),
                        name=name,
                        arguments=dict(call_args) if isinstance(call_args, dict) else {},
                        arguments_summary="",
                    )
    elif ep == "phase.act.fold.start":
        _record_phase(state, "act", ts, event)
    elif ep in PHASE_FOLD_EPS:
        _record_phase(state, PHASE_FOLD_EPS[ep], ts, event)
        if ep == "phase.think.fold":
            target = state.open_step
            if target is None and state.closed_frames:
                target = state.closed_frames[-1]
            if target is not None:
                target.thinking = _binding_engine().apply_thinking_patch(
                    target.thinking,
                    payload,
                    ep,
                    frame_model=target.model or "",
                )
                model = str(payload.get("objective") or "")
                if (
                    str(payload.get("objective_kind") or "") == "model_name"
                    and model
                    and not target.model
                ):
                    target.model = model
    elif ep == "step.thinking.record":
        target = state.open_step
        if target is not None:
            token_count = payload.get("token_count")
            target.thinking = ThinkingTrace(
                model=target.model,
                latency_ms=0,
                reasoning=str(payload.get("text_preview") or ""),
                raw_response_preview=str(
                    payload.get("content_path") or payload.get("content_digest") or ""
                ),
                completion_tokens=token_count if isinstance(token_count, int) else None,
            )
    elif ep == "critic.eval.start":
        _record_phase(state, "reflect", ts, event)
    elif ep == "critic.eval.end":
        _record_phase(state, "reflect", ts, event)
        if state.open_step is not None and state.open_step.phase == "act":
            _close_step(state, str(event.get("outcome") or "success"))
    elif ep in {
        "step.tool_call.record",
        "step.tool_result.record",
        "body.tool.execute.end",
    }:
        # body.tool.execute.start 与 step.tool_call.record 同义(invocation
        # / name / args 已由 record 携带),丢弃避免重复合并覆写前一次 tool。
        target = state.open_step
        if target is None and state.closed_frames:
            target = state.closed_frames[-1]
        if target is not None:
            if ep == "step.tool_call.record":
                _assign_tool_call(target, payload, ep)
            else:
                _assign_tool_result(target, payload, ep)
    elif ep == "exception.caught":
        _capture_exception(state, payload, ts)


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
        # run 已 completed 时,残留 open step 属正常收口;failed 标 failed;
        # 其余(中断 / 无终态信号)维持 cancelled。
        if state.terminal_outcome == "completed":
            residual_outcome = "success"
        elif state.terminal_outcome == "failed":
            residual_outcome = "failed"
        else:
            residual_outcome = "cancelled"
        _close_step(state, residual_outcome)
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
            outcome=_journal_step_outcome(f.outcome),
            error=f.error,
            extra={},
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
    # Totals 契约(lca/contracts/models/observability/journal_totals.py):
    # totals.segments == sum(len(s.segments) for s in steps) —— 只计已挂进
    # step 的 segment;无 step 可挂的 think/act fold 只进 phases 计数。
    seg_count = sum(len(f.segments) for f in state.closed_frames)
    return JournalDocument(
        schema="lca.journal/3.1",
        run_id=cast("RunId", run_id),
        trace_id=cast("TraceId", run_id),
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
        events: 可迭代事件,两路形态均可:spine 形态(:class:`EventRecord` /
            含 ``execution_point`` 的 Mapping,裸 EP)与 Session 形态
            (:class:`SessionEvent` / 含 ``type`` + ``data`` 的 Mapping,
            ``spine.*`` CATEGORY 前缀经反查表归一为裸 EP)。非 fold 目标
            的事件被 skip(不抛)。
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
