"""Agent journal → four live UI SSE events (ADR-0100).

Single-direction translator: journal dataclasses → SSE frames with
``event: reasoning|text|tool|done``. Gateway owns one encoder per live
subscription. Keepalive stays at the HTTP layer (LiveTail).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, Protocol

from lca.contracts.observability.status import RunLifecycleStatus

_OUTPUT_TRUNCATE = 2000


class _SupportsEventType(Protocol):
    """Anything with a string ``event_type`` plus dataclass-y fields."""

    event_type: str


class RunUiEncoder:
    """Translate a journal event stream into four live UI SSE types."""

    REASONING_DELTA = "ReasoningDelta"
    STEP_TEXT_DELTA = "StepTextDelta"
    TOOL_STARTED = "ToolStarted"
    TOOL_INVOKED = "ToolInvoked"
    TOOL_DENIED = "ToolDenied"
    DECISION_MADE = "DecisionMade"
    AGENT_RUN_FINISHED = "AgentRunFinished"
    TEAM_RUN_FINISHED = "TeamRunFinished"

    async def encode(
        self,
        stream: AsyncIterator[_SupportsEventType],
    ) -> AsyncIterator[bytes]:
        """Yield SSE frames until root ``done``, then end the generator."""
        emitted_text = False
        async for item in stream:
            seq = int(getattr(item, "seq", 0) or 0)
            event = getattr(item, "event", item)
            et = getattr(event, "event_type", "") or type(event).__name__

            if et == self.REASONING_DELTA:
                token = str(getattr(event, "text_delta", "") or "")
                if not token:
                    continue
                yield self._frame(seq, "reasoning", {"text": token})

            elif et == self.STEP_TEXT_DELTA:
                if getattr(event, "channel", "decision") != "answer":
                    continue
                token = str(getattr(event, "text_delta", "") or "")
                if not token:
                    continue
                emitted_text = True
                yield self._frame(seq, "text", {"text": token})

            elif et == self.TOOL_STARTED:
                yield self._frame(
                    seq,
                    "tool",
                    self._tool_payload(
                        event, phase="started", detail=self._extract_arguments(event)
                    ),
                )

            elif et == self.TOOL_INVOKED:
                yield self._frame(
                    seq,
                    "tool",
                    self._tool_payload(event, phase="done", detail=self._tool_done_detail(event)),
                )

            elif et == self.TOOL_DENIED:
                reason = str(getattr(event, "reason", "") or "")
                yield self._frame(
                    seq,
                    "tool",
                    self._tool_payload(event, phase="denied", detail=reason),
                )

            elif et == self.DECISION_MADE:
                if emitted_text:
                    continue
                text = str(getattr(event, "response_text", "") or "")
                if not text:
                    continue
                emitted_text = True
                yield self._frame(seq, "text", {"text": text})

            elif et == self.AGENT_RUN_FINISHED and self._parent_run_id(item) is not None:
                continue

            elif et in {self.AGENT_RUN_FINISHED, self.TEAM_RUN_FINISHED}:
                output = str(getattr(event, "output_text", "") or "")
                error = str(getattr(event, "error", "") or "")
                if not emitted_text and output:
                    emitted_text = True
                    yield self._frame(seq, "text", {"text": output})
                status = self._map_status(str(getattr(event, "status", "") or ""))
                done_payload: dict[str, Any] = {"status": status}
                if not emitted_text and error:
                    done_payload["error"] = error
                yield self._frame(seq, "done", done_payload)
                return

    @staticmethod
    def _frame(seq: int, event: str, data: dict[str, Any]) -> bytes:
        payload = json.dumps(data, ensure_ascii=False, default=str)
        return f"id: {seq}\nevent: {event}\ndata: {payload}\n\n".encode()

    @staticmethod
    def _map_status(status: str) -> str:
        """归一化终态事件 status 到 LobeHub UI ``done`` 帧词表。

        输入是终态事件 wire 词表(``RunLifecycleStatus`` 规范值 +
        A2A / UI 别名);输出是 UI 词表闭集(``awaiting_human`` /
        ``canceled`` / ``failed`` / ``completed``),不是生命周期 enum。
        """
        key = status.strip().lower()
        if key in {
            RunLifecycleStatus.WAITING_INPUT.value,
            RunLifecycleStatus.PAUSED.value,
            "awaiting_human",
            "input_required",
        }:
            return "awaiting_human"
        if key in {RunLifecycleStatus.CANCELLED.value, "cancelled"}:
            return "canceled"
        if key in {RunLifecycleStatus.FAILED.value, "error"}:
            return "failed"
        if key in {RunLifecycleStatus.COMPLETED.value, ""}:
            return "completed"
        if "wait" in key or "human" in key or "input" in key:
            return "awaiting_human"
        return "completed"

    @staticmethod
    def _parent_run_id(item: object) -> object | None:
        scope = getattr(item, "scope", None)
        return None if scope is None else getattr(scope, "parent_run_id", None)

    @staticmethod
    def _tool_done_detail(event: Any) -> str:
        if bool(getattr(event, "ok", True)) is False:
            return str(getattr(event, "error", "") or "tool failed")
        output = str(getattr(event, "output_text", "") or "")
        if output:
            if len(output) > _OUTPUT_TRUNCATE:
                return output[:_OUTPUT_TRUNCATE]
            return output
        return "ok"

    @classmethod
    def _tool_payload(cls, event: Any, *, phase: str, detail: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": str(getattr(event, "tool_name", "") or "tool"),
            "phase": phase,
            "detail": detail,
        }
        invocation = str(getattr(event, "invocation_id", "") or "")
        if invocation:
            payload["id"] = invocation
        state = cls._event_state(event)
        if state:
            payload["state"] = state
        if phase == "done":
            payload["ok"] = bool(getattr(event, "ok", True))
            error = str(getattr(event, "error", "") or "")
            if error:
                payload["error"] = error
        return payload

    @staticmethod
    def _event_state(event: Any) -> dict[str, Any]:
        """ADR-0101 PR-3:tool 事件事实字段只有 ``arguments`` / ``files`` /
        ``ok`` / ``error`` / ``invocation_id`` / ``tool_name``。参数完整原文
        由 ``arguments``(inline 退路)或 ``arguments_ref``(evidence)给出;
        UI 渲染按 ``tool_name`` 派发到 LobeHub renderer registry。
        """
        collected: dict[str, Any] = dict(getattr(event, "arguments", {}) or {})
        files = getattr(event, "files", None)
        if files and "files" not in collected:
            collected["files"] = list(files)
        return collected

    @staticmethod
    def _extract_arguments(event: Any) -> str:
        """Serialize tool arguments as a compact JSON string.

        ADR-0101 PR-3:ToolStarted.arguments 是事实字段;evidence 路径下
        ``arguments_ref`` 由 LobeHub renderer 按 ref 单独 fetch。
        """
        collected: dict[str, Any] = dict(getattr(event, "arguments", {}) or {})
        return json.dumps(collected, ensure_ascii=False, default=str)


__all__ = ["RunUiEncoder"]
