"""TimelineProjection — 纯领域映射。

Journal StampedEvent → Timeline 领域事件。

设计原则：
  1. 输出是领域中立结构
     - tool 事件用 LCA 内部名 (execute_code)，不是 wire 名 (lca____executeCode)
     - file 事件保留原始路径，不拼 gateway URL
     - plugin_state 只保留原始 plugin_state，不拼装 LobeHub 特有字段
  2. 过滤在这里做（RunInsight / decision channel 不产生 timeline 事件）
  3. 声明式 dispatch table，新增事件类型只加一行

不做的事：
  - 不 resolve_tool_wire()（Adapter 层）
  - 不 build_tool_plugin_state()（Adapter 层）
  - 不 absolutize_file_parts()（Adapter 层）
  - 不 transform_tool_arguments()（Adapter 层）
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import cast

from gateway.timeline.types import (
    AnswerDeltaEvent,
    RunEndEvent,
    RunStartEvent,
    ThinkingDeltaEvent,
    ThinkingEndEvent,
    TimelineEvent,
    ToolDeltaEvent,
    ToolEndEvent,
    ToolStartEvent,
)
from lca.contracts.atoms.enums import StreamChannel
from lca.contracts.models.observability.journal import (
    AgentRunFinished,
    AgentRunStarted,
    DelegationCompleted,
    DelegationIssued,
    JournalEvent,
    ReasoningCompleted,
    ReasoningDelta,
    SandboxOutputDelta,
    StampedEvent,
    StepTextDelta,
    TeamRunFinished,
    TeamRunStarted,
    ToolDenied,
    ToolInvoked,
    ToolStarted,
)

Handler = Callable[["TimelineProjection", StampedEvent], list[TimelineEvent]]


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "\u2026"


@dataclass
class TimelineProjection:
    """Journal StampedEvent → Timeline 领域事件。

    纯映射，无副作用，不关心前端协议。
    """

    dropped: Counter[str] = field(default_factory=Counter)
    _finished: bool = False
    _reasoning: dict[int, str] = field(default_factory=dict)
    _answer: str = ""
    _invocation_ids: dict[str, str] = field(default_factory=dict)

    def project(self, stamped: StampedEvent) -> list[TimelineEvent]:
        """纯映射。每个 TimelineEvent 是领域中立 frozen dataclass。

        seq 赋值规则：
          - 1:1 映射的事件直接继承 stamped.seq
          - 1:N 映射的事件共享 stamped.seq
        """
        if self._finished:
            return []
        event = stamped.event

        # 过滤：RunInsight 和 decision channel 不产生 timeline 事件
        # RunInsight 由 insight_engine 处理，不在此投影
        from lca.contracts.models.observability.journal import RunInsight

        if isinstance(event, RunInsight):
            return []

        handler = _HANDLERS.get(type(event))
        if handler is None:
            self.dropped[type(event).__name__] += 1
            return []

        out = handler(self, stamped)
        # 赋值 seq
        result: list[TimelineEvent] = []
        for ev in out:
            result.append(_with_seq(ev, stamped.seq))
        return result


def _with_seq(event: TimelineEvent, seq: int) -> TimelineEvent:
    """Replace the default seq=0 with the actual stamped seq.

    Since these are frozen dataclasses, we use dataclasses.replace.
    """
    from dataclasses import replace

    if event.seq == 0 and seq != 0:
        return replace(event, seq=seq)
    return event


# ── Handlers ──────────────────────────────────────────────


def _run_start(p: TimelineProjection, s: StampedEvent) -> list[TimelineEvent]:
    ev = s.event
    preview = ""
    if isinstance(ev, AgentRunStarted):
        preview = ev.objective_preview or ev.objective or ""
    return [
        RunStartEvent(
            run_id=s.scope.run_id,
            trace_id=s.scope.trace_id,
            objective_preview=preview[:200],
        )
    ]


def _thinking_delta(p: TimelineProjection, s: StampedEvent) -> list[TimelineEvent]:
    ev = cast("ReasoningDelta", s.event)
    text = ev.text_delta or ""
    if not text:
        return []
    p._reasoning[ev.step] = p._reasoning.get(ev.step, "") + text
    return [ThinkingDeltaEvent(step=ev.step, text=text)]


def _thinking_end(p: TimelineProjection, s: StampedEvent) -> list[TimelineEvent]:
    ev = cast("ReasoningCompleted", s.event)
    content = p._reasoning.pop(ev.step, "") or (ev.content_preview or "")
    return [ThinkingEndEvent(step=ev.step, content=content, duration_ms=ev.duration_ms)]


def _answer_delta(p: TimelineProjection, s: StampedEvent) -> list[TimelineEvent]:
    ev = cast("StepTextDelta", s.event)
    # 过滤：decision channel 不产生 timeline 事件
    if ev.channel == StreamChannel.DECISION.value:
        return []
    text = ev.text_delta or ""
    if not text:
        return []
    p._answer += text
    return [AnswerDeltaEvent(step=ev.step, text=text)]


def _delegation_issued(p: TimelineProjection, s: StampedEvent) -> list[TimelineEvent]:
    ev = cast("DelegationIssued", s.event)
    text = f"\n\n\u21e2 **\u59d4\u6d3e** \u2192 `{ev.callee_role}`: {ev.subtask_preview}\n"
    p._answer += text
    return [AnswerDeltaEvent(step=-1, text=text)]


def _delegation_done(p: TimelineProjection, s: StampedEvent) -> list[TimelineEvent]:
    ev = cast("DelegationCompleted", s.event)
    status = "\u2705" if ev.ok else "\u274c"
    preview = _truncate(ev.output_text or "", 500)
    text = f"\n\n\u21e0 **\u59d4\u6d3e\u5b8c\u6210** {status}: {preview}\n"
    p._answer += text
    return [AnswerDeltaEvent(step=-1, text=text)]


def _tool_start(p: TimelineProjection, s: StampedEvent) -> list[TimelineEvent]:
    ev = cast("ToolStarted", s.event)
    inv = ev.invocation_id or ""
    tool_call_id = f"call_{inv}" if inv else f"call_{len(p._invocation_ids)}"
    if inv:
        p._invocation_ids[inv] = tool_call_id

    # 保留原始 arguments 和 plugin_state，不做 wire 翻译
    args_preview = ev.arguments_preview or "{}"
    import json

    try:
        arguments = json.loads(args_preview) if isinstance(args_preview, str) else args_preview
    except (json.JSONDecodeError, TypeError):
        arguments = {}

    plugin_state = dict(ev.plugin_state or {})

    out: list[TimelineEvent] = [
        ToolStartEvent(
            tool_call_id=tool_call_id,
            tool_name=ev.tool_name,
            arguments=arguments if isinstance(arguments, dict) else {},
            plugin_state=plugin_state,
        )
    ]

    # sandbox 工具种子 tool.delta（保留原始 plugin_state）
    if plugin_state:
        seed = dict(plugin_state)
        seed.setdefault("executionEnv", "sandbox")
        seed.setdefault("success", True)
        out.append(
            ToolDeltaEvent(
                tool_call_id=tool_call_id,
                stream="stdout",
                text="",
                plugin_state=seed,
            )
        )
    return out


def _tool_delta(p: TimelineProjection, s: StampedEvent) -> list[TimelineEvent]:
    ev = cast("SandboxOutputDelta", s.event)
    inv = ev.invocation_id
    if not inv:
        return []
    tool_call_id = p._invocation_ids.get(inv)
    if not tool_call_id:
        return []

    return [
        ToolDeltaEvent(
            tool_call_id=tool_call_id,
            stream=ev.stream,
            text=ev.text_delta or "",
            plugin_state={"seq": ev.seq},
        )
    ]


def _tool_end(p: TimelineProjection, s: StampedEvent) -> list[TimelineEvent]:
    ev = cast("ToolInvoked", s.event)
    inv = ev.invocation_id or ""
    tool_call_id = p._invocation_ids.pop(inv, "") or f"call_{inv or 'unknown'}"
    if inv:
        p._invocation_ids.pop(inv, None)

    # 保留原始 plugin_state 和 files，不做 wire 翻译
    plugin_state = dict(ev.plugin_state or {})
    plugin_state["success"] = ev.ok
    if not ev.ok and ev.error:
        plugin_state["errorDetail"] = ev.error
        plugin_state.setdefault("error", ev.error)

    # 保留原始文件列表，不做 URL absolutize
    files = [dict(f) for f in (ev.files or ())]

    result = ToolEndEvent(
        tool_call_id=tool_call_id,
        tool_name=ev.tool_name,
        ok=ev.ok,
        content=ev.result_preview or "",
        plugin_state=plugin_state,
        latency_ms=ev.latency_ms,
        error=ev.error or "",
        files=files,
    )
    return [result]


def _tool_denied(p: TimelineProjection, s: StampedEvent) -> list[TimelineEvent]:
    ev = cast("ToolDenied", s.event)
    text = f"\n\n> **{ev.tool_name}** \u26d4 {ev.reason}\n"
    p._answer += text
    return [AnswerDeltaEvent(step=-1, text=text)]


def _run_end(p: TimelineProjection, s: StampedEvent) -> list[TimelineEvent]:
    ev = cast("AgentRunFinished | TeamRunFinished", s.event)
    p._finished = True
    out: list[TimelineEvent] = []
    final = (ev.output_text or "").strip()
    if final and final not in p._answer:
        suffix = final if not p._answer else f"\n\n{final}"
        p._answer += suffix
        out.append(AnswerDeltaEvent(step=-1, text=suffix))
    out.append(
        RunEndEvent(
            status=ev.status or "completed",
            steps=ev.steps,
            output=ev.output_text or "",
            error=ev.error or "",
        )
    )
    return out


# 声明式 dispatch table
_HANDLERS: dict[type[JournalEvent], Handler] = {
    AgentRunStarted: _run_start,
    TeamRunStarted: _run_start,
    ReasoningDelta: _thinking_delta,
    ReasoningCompleted: _thinking_end,
    StepTextDelta: _answer_delta,
    DelegationIssued: _delegation_issued,
    DelegationCompleted: _delegation_done,
    ToolStarted: _tool_start,
    SandboxOutputDelta: _tool_delta,
    ToolInvoked: _tool_end,
    ToolDenied: _tool_denied,
    AgentRunFinished: _run_end,
    TeamRunFinished: _run_end,
}
