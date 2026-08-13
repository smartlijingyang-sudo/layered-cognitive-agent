"""LobeHub 前端协议适配器。

将 Timeline 领域事件翻译为 LobeHub 前端 UI 需要的格式：
  - tool_name → wire_name (identifier____apiName)
  - arguments → transform_tool_arguments(wire)
  - plugin_state → build_tool_plugin_state(wire, ...)
  - files → absolutize_file_parts()

如果未来换前端（自建 SPA / CLI / API），写一个新的 adapter，这一层整体替换。
TimelineProjection 一行不改。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from gateway.lobehub_bridge.file_urls import absolutize_file_parts
from gateway.lobehub_bridge.lobehub_adapter import (
    build_tool_plugin_state,
    resolve_tool_wire,
    split_wire_name,
    tool_result_content,
    tool_result_preview_limit,
    transform_tool_arguments,
)
from gateway.lobehub_bridge.lobehub_adapter.tool_spec import (
    parse_args_json,
    safe_json_string,
)
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
from lca.layer0_infra.computer.constants import STREAMING_WIRE_APIS
from lca.layer1_cognitive.body.tool_ui_state import wire_arguments_json


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "\u2026"


@dataclass
class LobeHubSSEAdapter:
    """LobeHub SSE 协议适配器。

    有状态适配器，一个实例严格绑定一个 run stream。
    不可跨 stream 复用：实例内部维护的累积状态与特定 run 的工具调用上下文绑定。

    生命周期：由 compose_sse_stream() 创建，随 HTTP 连接关闭而释放。
    """

    _invocation_ids: dict[str, str] = field(default_factory=dict, init=False)
    _pending: dict[str, dict[str, Any]] = field(default_factory=dict, init=False)
    _exec_buf: dict[str, dict[str, str]] = field(default_factory=dict, init=False)

    def adapt(self, event: TimelineEvent) -> list[dict[str, Any]]:
        """将一个领域事件翻译为 0~N 个 LobeHub SSE payload dict。

        每个 dict 可直接传给 encode_sse。
        这是唯一知道 wire_name / plugin_state / file URL 的地方。
        """
        match event:
            case RunStartEvent():
                return [self._adapt_run_start(event)]
            case ThinkingDeltaEvent():
                return [self._adapt_thinking_delta(event)]
            case ThinkingEndEvent():
                return [self._adapt_thinking_end(event)]
            case AnswerDeltaEvent():
                return [self._adapt_answer_delta(event)]
            case ToolStartEvent():
                return self._adapt_tool_start(event)
            case ToolDeltaEvent():
                return self._adapt_tool_delta(event)
            case ToolEndEvent():
                return self._adapt_tool_end(event)
            case RunEndEvent():
                return [self._adapt_run_end(event)]
        return []  # pragma: no cover — exhaustiveness

    def _adapt_run_start(self, event: RunStartEvent) -> dict[str, Any]:
        return {
            "type": "run.start",
            "run_id": event.run_id,
            "trace_id": event.trace_id,
            "objective_preview": event.objective_preview,
        }

    def _adapt_thinking_delta(self, event: ThinkingDeltaEvent) -> dict[str, Any]:
        return {"type": "thinking.delta", "step": event.step, "text": event.text}

    def _adapt_thinking_end(self, event: ThinkingEndEvent) -> dict[str, Any]:
        return {
            "type": "thinking.end",
            "step": event.step,
            "content": event.content,
            "duration_ms": event.duration_ms,
        }

    def _adapt_answer_delta(self, event: AnswerDeltaEvent) -> dict[str, Any]:
        return {"type": "answer.delta", "step": event.step, "text": event.text}

    def _adapt_tool_start(self, event: ToolStartEvent) -> list[dict[str, Any]]:
        full_args = (
            safe_json_string(event.arguments)
            if isinstance(event.arguments, str)
            else json.dumps(event.arguments, ensure_ascii=False, default=str)
        )
        wire = resolve_tool_wire(event.tool_name, full_args)
        wire_name = wire.wire_name if wire else event.tool_name
        args_json = (
            transform_tool_arguments(wire, full_args) if wire else safe_json_string(event.arguments)
        )
        identifier, api_name = split_wire_name(wire_name)

        tool_call_id = event.tool_call_id
        self._invocation_ids[tool_call_id] = tool_call_id
        self._pending[tool_call_id] = {
            "tool_call_id": tool_call_id,
            "name": event.tool_name,
            "wire_arguments": full_args,
            "plugin_state": dict(event.plugin_state),
        }

        out: list[dict[str, Any]] = [
            {
                "type": "tool.start",
                "tool_call_id": tool_call_id,
                "name": event.tool_name,
                "wire_name": wire_name,
                "identifier": identifier,
                "api_name": api_name,
                "arguments": args_json,
                "state": dict(event.plugin_state),
            }
        ]

        # sandbox 工具种子 tool.delta
        started_state = dict(event.plugin_state)
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

    def _adapt_tool_delta(self, event: ToolDeltaEvent) -> list[dict[str, Any]]:
        tool_call_id = event.tool_call_id
        pending = self._pending.get(tool_call_id)
        if pending is None:
            return []

        buf = self._exec_buf.setdefault(tool_call_id, {"stdout": "", "stderr": ""})
        key = "stderr" if event.stream == "stderr" else "stdout"
        buf[key] = buf.get(key, "") + (event.text or "")

        wire = resolve_tool_wire(pending["name"], pending["wire_arguments"])
        if wire is None or wire.api_name not in STREAMING_WIRE_APIS:
            return []

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
                "stream": event.stream,
                "text": event.text,
                "state": state,
                "snapshot_seq": event.seq,
            }
        ]

    def _adapt_tool_end(self, event: ToolEndEvent) -> list[dict[str, Any]]:
        tool_call_id = event.tool_call_id
        pending = self._pending.pop(tool_call_id, None)
        exec_buf = self._exec_buf.pop(tool_call_id, None)

        lca_name = event.tool_name or (pending or {}).get("name", "")
        args_preview = (pending or {}).get("wire_arguments", "{}")
        wire_args = wire_arguments_json(
            arguments_preview=args_preview,
            plugin_state=event.plugin_state or (pending or {}).get("plugin_state"),
        )
        wire = resolve_tool_wire(lca_name, wire_args)
        limit = tool_result_preview_limit(lca_name)
        preview = _truncate(event.content or "", limit)

        # 构建 LobeHub plugin state
        if event.plugin_state and event.plugin_state.get("success") is not None:
            state = dict(event.plugin_state)
        elif wire:
            state = build_tool_plugin_state(
                wire,
                arguments_preview=wire_args,
                result_preview=preview,
                ok=event.ok,
                error=event.error or "",
            )
        else:
            state = {"success": event.ok, "error": event.error or ""}

        if not event.ok and event.error:
            state["errorDetail"] = event.error
            state.setdefault("error", event.error)
        else:
            state["success"] = event.ok

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

        file_parts = absolutize_file_parts(event.files or ())
        if file_parts:
            state["files"] = file_parts

        content = tool_result_content(
            preview, ok=event.ok, error=event.error or "", lca_tool_name=lca_name
        )
        if lca_name == "activate_skill" and isinstance(state.get("content"), str):
            content = state["content"]
        if not content and state.get("output"):
            content = str(state["output"])[:limit]

        result: dict[str, Any] = {
            "type": "tool.end",
            "tool_call_id": tool_call_id,
            "name": lca_name,
            "ok": event.ok,
            "content": content,
            "state": state,
            "latency_ms": event.latency_ms,
        }
        if not event.ok and event.error:
            result["error"] = event.error
        if file_parts:
            result["files"] = file_parts
        return [result]

    def _adapt_run_end(self, event: RunEndEvent) -> dict[str, Any]:
        return {
            "type": "run.end",
            "status": event.status,
            "steps": event.steps,
            "output": event.output,
            "error": event.error,
        }
