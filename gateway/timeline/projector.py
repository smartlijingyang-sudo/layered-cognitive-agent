"""Declarative journal → timeline.v1 projection.

Unknown journal types are dropped (counted on the instance). No asdict passthrough.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, cast

from gateway.lobehub_bridge.file_urls import absolutize_file_parts
from gateway.lobehub_bridge.lobehub_adapter import (
    build_tool_plugin_state,
    resolve_tool_wire,
    split_wire_name,
    tool_result_content,
    tool_result_preview_limit,
    transform_tool_arguments,
)
from gateway.lobehub_bridge.lobehub_adapter.json_helpers import safe_json_string
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
from lca.layer0_infra.computer.constants import STREAMING_WIRE_APIS
from lca.layer1_cognitive.body.tool_ui_state import wire_arguments_json

TimelineEvent = dict[str, Any]
Handler = Callable[["TimelineProjector", StampedEvent], list[TimelineEvent]]


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "…"


@dataclass
class TimelineProjector:
    """Stateful projector: one instance per run stream."""

    dropped: Counter[str] = field(default_factory=Counter)
    _finished: bool = False
    _reasoning: dict[int, str] = field(default_factory=dict)
    _answer: str = ""
    _invocation_ids: dict[str, str] = field(default_factory=dict)
    _pending: dict[str, dict[str, Any]] = field(default_factory=dict)
    _exec_buf: dict[str, dict[str, str]] = field(default_factory=dict)

    def project(self, stamped: StampedEvent) -> list[TimelineEvent]:
        if self._finished:
            return []
        event = stamped.event
        handler = _HANDLERS.get(type(event))
        if handler is None:
            self.dropped[type(event).__name__] += 1
            return []
        out = handler(self, stamped)
        for ev in out:
            ev.setdefault("seq", stamped.seq)
            if stamped.scope.run_id:
                ev.setdefault("run_id", stamped.scope.run_id)
        return out


def _run_start(p: TimelineProjector, s: StampedEvent) -> list[TimelineEvent]:
    ev = s.event
    preview = ""
    if isinstance(ev, AgentRunStarted):
        preview = ev.objective_preview or ev.objective or ""
    return [
        {
            "type": "run.start",
            "run_id": s.scope.run_id,
            "trace_id": s.scope.trace_id,
            "objective_preview": preview[:200],
        }
    ]


def _thinking_delta(p: TimelineProjector, s: StampedEvent) -> list[TimelineEvent]:
    ev = cast("ReasoningDelta", s.event)
    text = ev.text_delta or ""
    if not text:
        return []
    p._reasoning[ev.step] = p._reasoning.get(ev.step, "") + text
    return [{"type": "thinking.delta", "step": ev.step, "text": text}]


def _thinking_end(p: TimelineProjector, s: StampedEvent) -> list[TimelineEvent]:
    ev = cast("ReasoningCompleted", s.event)
    content = p._reasoning.pop(ev.step, "") or (ev.content_preview or "")
    return [
        {
            "type": "thinking.end",
            "step": ev.step,
            "content": content,
            "duration_ms": ev.duration_ms,
        }
    ]


def _answer_delta(p: TimelineProjector, s: StampedEvent) -> list[TimelineEvent]:
    ev = cast("StepTextDelta", s.event)
    if ev.channel != StreamChannel.ANSWER.value:
        return []
    text = ev.text_delta or ""
    if not text:
        return []
    p._answer += text
    return [{"type": "answer.delta", "step": ev.step, "text": text}]


def _delegation_issued(p: TimelineProjector, s: StampedEvent) -> list[TimelineEvent]:
    ev = cast("DelegationIssued", s.event)
    text = f"\n\n⇢ **委派** → `{ev.callee_role}`: {ev.subtask_preview}\n"
    p._answer += text
    return [{"type": "answer.delta", "step": -1, "text": text}]


def _delegation_done(p: TimelineProjector, s: StampedEvent) -> list[TimelineEvent]:
    ev = cast("DelegationCompleted", s.event)
    status = "✅" if ev.ok else "❌"
    preview = _truncate(ev.output_text or "", 500)
    text = f"\n\n⇠ **委派完成** {status}: {preview}\n"
    p._answer += text
    return [{"type": "answer.delta", "step": -1, "text": text}]


def _tool_start(p: TimelineProjector, s: StampedEvent) -> list[TimelineEvent]:
    ev = cast("ToolStarted", s.event)
    inv = ev.invocation_id or ""
    tool_call_id = f"call_{inv}" if inv else f"call_{len(p._invocation_ids)}"
    if inv:
        p._invocation_ids[inv] = tool_call_id

    args_preview = ev.arguments_preview or "{}"
    started_state = dict(ev.plugin_state or {})
    full_args = wire_arguments_json(
        arguments_preview=args_preview,
        plugin_state=started_state,
    )
    wire = resolve_tool_wire(ev.tool_name, full_args)
    function_name = wire.wire_name if wire else ev.tool_name
    args_json = transform_tool_arguments(wire, full_args) if wire else safe_json_string(full_args)
    identifier, api_name = split_wire_name(function_name)

    p._pending[inv or tool_call_id] = {
        "tool_call_id": tool_call_id,
        "name": ev.tool_name,
        "wire_arguments": full_args,
        "plugin_state": started_state,
    }

    out: list[TimelineEvent] = [
        {
            "type": "tool.start",
            "tool_call_id": tool_call_id,
            "name": ev.tool_name,
            "wire_name": function_name,
            "identifier": identifier,
            "api_name": api_name,
            "arguments": args_json,
            "state": started_state,
        }
    ]
    # Seed streaming card body for sandbox tools
    if started_state and wire and wire.api_name in STREAMING_WIRE_APIS:
        seed = dict(started_state)
        seed.setdefault("executionEnv", "sandbox")
        seed.setdefault("success", True)
        out.append(
            {
                "type": "tool.delta",
                "tool_call_id": tool_call_id,
                "stream": "stdout",
                "text": "",
                "state": seed,
                "snapshot_seq": 0,
            }
        )
    return out


def _tool_delta(p: TimelineProjector, s: StampedEvent) -> list[TimelineEvent]:
    ev = cast("SandboxOutputDelta", s.event)
    inv = ev.invocation_id
    if not inv:
        return []
    tool_call_id = p._invocation_ids.get(inv)
    pending = p._pending.get(inv)
    if not tool_call_id or pending is None:
        return []

    buf = p._exec_buf.setdefault(inv, {"stdout": "", "stderr": ""})
    key = "stderr" if ev.stream == "stderr" else "stdout"
    buf[key] = buf.get(key, "") + (ev.text_delta or "")

    wire = resolve_tool_wire(pending["name"], pending["wire_arguments"])
    if wire is None or wire.api_name not in STREAMING_WIRE_APIS:
        return []

    from gateway.lobehub_bridge.lobehub_adapter.json_helpers import parse_args_json

    args = wire.transform_args(parse_args_json(pending["wire_arguments"]))
    state: dict[str, Any] = {
        "executionEnv": "sandbox",
        "stdout": buf.get("stdout", ""),
        "stderr": buf.get("stderr", ""),
        "success": True,
        "output": buf.get("stdout") or buf.get("stderr") or "",
    }
    for k in ("code", "command", "language", "description"):
        if k in pending.get("plugin_state", {}):
            state[k] = pending["plugin_state"][k]
    if wire.api_name == "executeCode":
        state["output"] = buf.get("stdout", "")
        state["language"] = args.get("language", state.get("language", "python"))
        code = args.get("code") or state.get("code")
        if isinstance(code, str) and code:
            state["code"] = code
    else:
        command = args.get("command") or state.get("command", "")
        state["command"] = command
        state["output"] = buf.get("stdout") or buf.get("stderr") or ""

    return [
        {
            "type": "tool.delta",
            "tool_call_id": tool_call_id,
            "stream": ev.stream,
            "text": ev.text_delta or "",
            "state": state,
            "snapshot_seq": ev.seq,
        }
    ]


def _tool_end(p: TimelineProjector, s: StampedEvent) -> list[TimelineEvent]:
    ev = cast("ToolInvoked", s.event)
    inv = ev.invocation_id or ""
    pending = p._pending.pop(inv, None) if inv else None
    tool_call_id = (
        (pending or {}).get("tool_call_id")
        or p._invocation_ids.pop(inv, "")
        or f"call_{inv or 'unknown'}"
    )
    exec_buf = p._exec_buf.pop(inv, None) if inv else None
    if inv:
        p._invocation_ids.pop(inv, None)

    args_preview = ev.arguments_preview or (pending or {}).get("wire_arguments", "{}")
    lca_name = ev.tool_name or (pending or {}).get("name", "")
    wire_args = (pending or {}).get("wire_arguments") or wire_arguments_json(
        arguments_preview=args_preview,
        plugin_state=ev.plugin_state or (pending or {}).get("plugin_state"),
    )
    wire = resolve_tool_wire(lca_name, wire_args)
    limit = tool_result_preview_limit(lca_name)
    preview = _truncate(ev.result_preview or "", limit)

    if ev.plugin_state:
        state = dict(ev.plugin_state)
        state["success"] = ev.ok
        if not ev.ok and ev.error:
            state["errorDetail"] = ev.error
            state.setdefault("error", ev.error)
    elif wire:
        state = build_tool_plugin_state(
            wire,
            arguments_preview=wire_args,
            result_preview=preview,
            ok=ev.ok,
            error=ev.error or "",
        )
    else:
        state = {"success": ev.ok, "error": ev.error or ""}

    if exec_buf:
        if exec_buf.get("stdout"):
            state["stdout"] = exec_buf["stdout"]
            state.setdefault("output", exec_buf["stdout"])
        if exec_buf.get("stderr"):
            state["stderr"] = exec_buf["stderr"]

    if pending:
        for k in ("code", "command", "language"):
            if k not in state and k in pending.get("plugin_state", {}):
                state[k] = pending["plugin_state"][k]

    file_parts = absolutize_file_parts(ev.files or ())
    # Single source of truth for files
    if file_parts:
        state["files"] = file_parts

    content = tool_result_content(preview, ok=ev.ok, error=ev.error or "", lca_tool_name=lca_name)
    if lca_name == "activate_skill" and isinstance(state.get("content"), str):
        content = state["content"]
    if not content and state.get("output"):
        content = str(state["output"])[:limit]

    result: TimelineEvent = {
        "type": "tool.end",
        "tool_call_id": tool_call_id,
        "name": lca_name,
        "ok": ev.ok,
        "content": content,
        "state": state,
        "latency_ms": ev.latency_ms,
    }
    if not ev.ok and ev.error:
        result["error"] = ev.error
    if file_parts:
        result["files"] = file_parts
    return [result]


def _tool_denied(p: TimelineProjector, s: StampedEvent) -> list[TimelineEvent]:
    ev = cast("ToolDenied", s.event)
    text = f"\n\n> **{ev.tool_name}** ⛔ {ev.reason}\n"
    p._answer += text
    return [{"type": "answer.delta", "step": -1, "text": text}]


def _run_end(p: TimelineProjector, s: StampedEvent) -> list[TimelineEvent]:
    ev = cast("AgentRunFinished | TeamRunFinished", s.event)
    p._finished = True
    out: list[TimelineEvent] = []
    final = (ev.output_text or "").strip()
    # Flush harvest summary before terminal event (never after).
    if final and final not in p._answer:
        suffix = final if not p._answer else f"\n\n{final}"
        p._answer += suffix
        out.append({"type": "answer.delta", "step": -1, "text": suffix})
    out.append(
        {
            "type": "run.end",
            "status": ev.status or "completed",
            "steps": ev.steps,
            "output": ev.output_text or "",
            "error": ev.error or "",
        }
    )
    return out


# Declarative dispatch table — extend only by adding rows here.
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
