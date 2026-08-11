"""Tool lifecycle projection — extracted from JournalOpenAiProjector.

Owns all tool-related mutable state (pending calls, exec buffers, invocation
IDs) and the four tool-event projection methods.  The main projector delegates
``ToolStarted`` / ``SandboxOutputDelta`` / ``ToolInvoked`` / ``ToolDenied``
to this handler, keeping its own field count manageable.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from gateway.lobehub_bridge.file_urls import absolutize_file_parts
from gateway.lobehub_bridge.lca_sse_extension import (
    lca_tool_result_event,
    lca_tool_started_event,
    lca_tool_state_event,
)
from gateway.lobehub_bridge.lobehub_adapter import (
    build_tool_plugin_state,
    resolve_tool_wire,
    split_wire_name,
    tool_result_content,
    tool_result_preview_limit,
    transform_tool_arguments,
)
from gateway.lobehub_bridge.lobehub_adapter.json_helpers import (
    parse_args_json,
    safe_json_string,
)
from gateway.lobehub_bridge.lobehub_adapter.protocol import TOOL_RESULT_PREVIEW_LIMIT
from lca.contracts.models.observability.journal import (
    SandboxOutputDelta,
    ToolDenied,
    ToolInvoked,
    ToolStarted,
)
from lca.layer0_infra.computer.constants import STREAMING_WIRE_APIS

# ── Internal data types ─────────────────────────────────────

Chunk = dict[str, Any]
EmitFn = Callable[[list[Chunk]], list[Chunk]]


@dataclass
class _PendingToolCall:
    tool_call_id: str
    index: int
    lca_tool_name: str
    arguments_preview: str


@dataclass
class _ExecBuffer:
    stdout: str = ""
    stderr: str = ""
    seq: int = 0


# ── Handler ─────────────────────────────────────────────────


@dataclass
class ToolProjection:
    """Manages tool lifecycle state and projects tool events to OpenAI chunks.

    The main projector creates one handler and delegates the four tool event
    types to it.  ``emit_lca`` and ``emit_delta`` callbacks route output back
    through the projector's chunk-formatting methods.
    """

    emit_lca: EmitFn
    emit_delta: EmitFn
    _tool_call_index: int = 0
    _pending_tools: dict[str, _PendingToolCall] = field(default_factory=dict)
    _invocation_tool_ids: dict[str, str] = field(default_factory=dict)
    _exec_buffers: dict[str, _ExecBuffer] = field(default_factory=dict)

    # ── Event projections ───────────────────────────────────

    def project_started(self, event: ToolStarted) -> list[Chunk]:
        idx = self._tool_call_index
        self._tool_call_index += 1
        tool_call_id = f"call_{event.invocation_id}" if event.invocation_id else f"call_{idx}"
        args_preview = event.arguments_preview or "{}"
        wire = resolve_tool_wire(event.tool_name, args_preview)
        function_name = wire.wire_name if wire else event.tool_name
        args_json = (
            transform_tool_arguments(wire, args_preview) if wire else safe_json_string(args_preview)
        )
        identifier, api_name = split_wire_name(function_name)
        if event.invocation_id:
            self._pending_tools[event.invocation_id] = _PendingToolCall(
                tool_call_id=tool_call_id,
                index=idx,
                lca_tool_name=event.tool_name,
                arguments_preview=args_preview,
            )
            self._invocation_tool_ids[event.invocation_id] = tool_call_id
        started = lca_tool_started_event(
            tool_call_id=tool_call_id,
            wire_name=function_name,
            identifier=identifier,
            api_name=api_name,
            arguments=args_json,
            lca_tool_name=event.tool_name,
        )
        return self.emit_lca([started])

    def project_sandbox_output(self, event: SandboxOutputDelta) -> list[Chunk]:
        inv_id = event.invocation_id
        if not inv_id:
            return []
        buf = self._exec_buffers.setdefault(inv_id, _ExecBuffer())
        buf.seq += 1
        if event.stream == "stderr":
            buf.stderr += event.text_delta
        else:
            buf.stdout += event.text_delta
        tool_call_id = self._invocation_tool_ids.get(inv_id)
        pending = self._pending_tools.get(inv_id)
        if not tool_call_id or pending is None:
            return []
        wire = resolve_tool_wire(pending.lca_tool_name, pending.arguments_preview)
        if wire is None or wire.api_name not in STREAMING_WIRE_APIS:
            return []
        args = wire.transform_args(parse_args_json(pending.arguments_preview))
        state: dict[str, Any] = {
            "executionEnv": "sandbox",
            "stdout": buf.stdout,
            "stderr": buf.stderr,
            "success": True,
        }
        if wire.api_name == "executeCode":
            state["output"] = buf.stdout
            state["language"] = args.get("language", "python")
            code = args.get("code")
            if isinstance(code, str) and code:
                state["code"] = code
        else:
            command = args.get("command", "")
            state["command"] = command
            state["output"] = buf.stdout or buf.stderr
        lca_event = lca_tool_state_event(
            tool_call_id=tool_call_id,
            state=state,
            snapshot_seq=buf.seq,
            content=buf.stdout or buf.stderr,
        )
        return self.emit_lca([lca_event])

    def project_invoked(self, event: ToolInvoked) -> list[Chunk]:
        inv_id = event.invocation_id
        pending = self._pending_tools.pop(inv_id, None) if inv_id else None
        tool_call_id = (
            pending.tool_call_id
            if pending
            else self._invocation_tool_ids.pop(inv_id, "")
            if inv_id
            else ""
        )
        exec_buf = self._exec_buffers.pop(inv_id, None) if inv_id else None
        if inv_id:
            self._invocation_tool_ids.pop(inv_id, None)

        args_preview = event.arguments_preview or (pending.arguments_preview if pending else "{}")
        lca_name = event.tool_name or (pending.lca_tool_name if pending else "")
        wire = resolve_tool_wire(lca_name, args_preview)

        if wire and tool_call_id:
            limit = tool_result_preview_limit(lca_name)
            preview = _truncate(event.result_preview, limit)
            if event.plugin_state:
                state = dict(event.plugin_state)
                state["success"] = event.ok
                if not event.ok and event.error:
                    state["errorDetail"] = event.error
            else:
                state = build_tool_plugin_state(
                    wire,
                    arguments_preview=args_preview,
                    result_preview=preview,
                    ok=event.ok,
                    error=event.error,
                )
            if exec_buf:
                if exec_buf.stdout:
                    state["stdout"] = exec_buf.stdout
                    state.setdefault("output", exec_buf.stdout)
                if exec_buf.stderr:
                    state["stderr"] = exec_buf.stderr
            file_parts = absolutize_file_parts(event.files or ())
            if file_parts:
                state["files"] = file_parts
            content = tool_result_content(
                preview, ok=event.ok, error=event.error, lca_tool_name=lca_name
            )
            if not content and state.get("output"):
                content = str(state["output"])[:limit]
            lca_event = lca_tool_result_event(
                tool_call_id=tool_call_id,
                content=content,
                state=state,
                error=event.error if not event.ok else None,
                files=file_parts,
            )
            return self.emit_lca([lca_event])

        if event.ok:
            preview = _truncate(event.result_preview, TOOL_RESULT_PREVIEW_LIMIT)
            text = f"\n\n> **{event.tool_name}** ✅ ({event.latency_ms}ms)\n> {preview}\n"
        else:
            text = f"\n\n> **{event.tool_name}** ❌ {event.error}\n"
        return self.emit_delta([{"content": text}])

    def project_denied(self, event: ToolDenied) -> list[Chunk]:
        text = f"\n\n> **{event.tool_name}** ⛔ {event.reason}\n"
        return self.emit_delta([{"content": text}])


# ── Shared utility ──────────────────────────────────────────


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "…"
