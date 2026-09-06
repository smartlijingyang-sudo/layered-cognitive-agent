"""Agent journal → four live UI SSE events (ADR-0100).

Single-direction translator: journal dataclasses → SSE frames with
``event: reasoning|text|tool|done``. Gateway owns one encoder per live
subscription. Keepalive stays at the HTTP layer (LiveTail).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any, Protocol, cast

from lca.contracts.models.observability.journal.journal import StampedEvent
from lca.contracts.observability.journal.run_journal import LiveRunProjection
from lca.contracts.observability.registry.status import RunLifecycleStatus

_OUTPUT_TRUNCATE = 2000
_HEARTBEAT = b": keepalive\n\n"
_CARRIER_TERMINAL_OPERATION = "run.lifecycle.failed"


class _SupportsEventType(Protocol):
    """Anything with a string ``event_type`` plus dataclass-y fields."""

    event_type: str


@dataclass
class _EncodeState:
    emitted_text: bool = False


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
    RUNTIME_OBSERVED = "RuntimeObserved"

    async def encode(
        self,
        stream: AsyncIterator[_SupportsEventType],
    ) -> AsyncIterator[bytes]:
        """Yield SSE frames until root ``done``, then end the generator."""
        state = _EncodeState()
        async for item in stream:
            frames, terminated = self._process_item(item, state)
            for frame in frames:
                yield frame
            if terminated:
                return

    async def encode_live_tail(
        self,
        tail: LiveRunProjection,
        *,
        after_seq: int = 0,
        heartbeat_s: float = 15.0,
        terminal_hint: Callable[[], tuple[str, str]] | None = None,
    ) -> AsyncIterator[bytes]:
        """Subscribe to a run tail and emit four UI events plus a terminal ``done``.

        Journal terminal facts (``AgentRunFinished`` / ``TeamRunFinished`` /
        carrier ``RuntimeObserved(run.lifecycle.failed)``) end the stream via
        ``_process_item``. When the tail closes without one, a synthetic ``done``
        may be emitted from ``terminal_hint()`` evaluated **at close time** —
        never inventing a failure while the carrier still reports ``running``.
        """
        from lca.infrastructure.observability.journal.stream.live_tail import (
            TEXT_CHANNEL_ANSWER,
            LiveGap,
            _is_visible_text_channel,
            encode_live_gap,
        )

        state = _EncodeState()
        terminated = False
        last_seq = after_seq
        sub = tail.subscribe(after_seq=after_seq)

        while True:
            try:
                item = await asyncio.wait_for(sub.__anext__(), timeout=heartbeat_s)
            except TimeoutError:
                yield _HEARTBEAT
                continue
            except StopAsyncIteration:
                break

            if isinstance(item, LiveGap):
                yield encode_live_gap(item)
                continue
            if not isinstance(item, StampedEvent):
                continue
            if not _is_visible_text_channel(item, TEXT_CHANNEL_ANSWER):
                continue

            last_seq = max(last_seq, item.seq)
            frames, item_terminated = self._process_item(cast("_SupportsEventType", item), state)
            for frame in frames:
                yield frame
            if item_terminated:
                terminated = True
                return

        if not terminated:
            status, error = terminal_hint() if terminal_hint is not None else ("", "")
            payload = self._synthetic_done_payload(
                terminal_status=status,
                terminal_error=error,
            )
            if payload is not None:
                yield self._frame(last_seq + 1, "done", payload)

    def synthetic_done_frame(
        self,
        seq: int,
        *,
        terminal_status: str = "",
        terminal_error: str = "",
    ) -> bytes:
        """Emit ``done`` when the journal stream ends without a terminal fact."""
        payload = self._synthetic_done_payload(
            terminal_status=terminal_status,
            terminal_error=terminal_error,
        )
        if payload is None:
            raise ValueError("synthetic_done_frame requires a terminal session status")
        return self._frame(seq, "done", payload)

    def _process_item(
        self,
        item: _SupportsEventType,
        state: _EncodeState,
    ) -> tuple[list[bytes], bool]:
        seq = int(getattr(item, "seq", 0) or 0)
        event = getattr(item, "event", item)
        et = getattr(event, "event_type", "") or type(event).__name__
        frames: list[bytes] = []

        if et == self.REASONING_DELTA:
            token = str(getattr(event, "text_delta", "") or "")
            if token:
                frames.append(self._frame(seq, "reasoning", {"text": token}))
            return frames, False

        if et == self.STEP_TEXT_DELTA:
            if getattr(event, "channel", "decision") != "answer":
                return frames, False
            token = str(getattr(event, "text_delta", "") or "")
            if token:
                state.emitted_text = True
                frames.append(self._frame(seq, "text", {"text": token}))
            return frames, False

        if et == self.TOOL_STARTED:
            frames.append(
                self._frame(
                    seq,
                    "tool",
                    self._tool_payload(
                        event, phase="started", detail=self._extract_arguments(event)
                    ),
                )
            )
            return frames, False

        if et == self.TOOL_INVOKED:
            frames.append(
                self._frame(
                    seq,
                    "tool",
                    self._tool_payload(event, phase="done", detail=self._tool_done_detail(event)),
                )
            )
            return frames, False

        if et == self.TOOL_DENIED:
            reason = str(getattr(event, "reason", "") or "")
            frames.append(
                self._frame(
                    seq,
                    "tool",
                    self._tool_payload(event, phase="denied", detail=reason),
                )
            )
            return frames, False

        if et == self.DECISION_MADE:
            if state.emitted_text:
                return frames, False
            text = str(getattr(event, "response_text", "") or "")
            if text:
                state.emitted_text = True
                frames.append(self._frame(seq, "text", {"text": text}))
            return frames, False

        if et == self.RUNTIME_OBSERVED:
            operation = str(getattr(event, "operation", "") or "")
            if operation == _CARRIER_TERMINAL_OPERATION:
                error = str(getattr(event, "error_message", "") or "").strip()
                status = str(
                    (getattr(event, "attributes", {}) or {}).get("status", "")
                    or RunLifecycleStatus.FAILED.value
                )
                frames.append(
                    self._frame(
                        seq,
                        "done",
                        self._terminal_done_payload(
                            status=status,
                            error=error,
                            emitted_text=state.emitted_text,
                        ),
                    )
                )
                return frames, True
            return frames, False

        if et == self.AGENT_RUN_FINISHED and self._parent_run_id(item) is not None:
            return frames, False

        if et in {self.AGENT_RUN_FINISHED, self.TEAM_RUN_FINISHED}:
            output = str(getattr(event, "output_text", "") or "")
            error = str(getattr(event, "error", "") or "")
            if not state.emitted_text and output:
                state.emitted_text = True
                frames.append(self._frame(seq, "text", {"text": output}))
            status = str(getattr(event, "status", "") or "")
            frames.append(
                self._frame(
                    seq,
                    "done",
                    self._terminal_done_payload(
                        status=status,
                        error=error,
                        emitted_text=state.emitted_text,
                    ),
                )
            )
            return frames, True

        return frames, False

    def _terminal_done_payload(
        self,
        *,
        status: str,
        error: str,
        emitted_text: bool,
    ) -> dict[str, Any]:
        mapped = self._map_status(status)
        payload: dict[str, Any] = {"status": mapped}
        err = error.strip()
        if err and (mapped == "failed" or not emitted_text):
            payload["error"] = err
        return payload

    def _synthetic_done_payload(
        self,
        *,
        terminal_status: str,
        terminal_error: str,
    ) -> dict[str, Any] | None:
        err = terminal_error.strip()
        if err:
            return {"status": "failed", "error": err}
        key = terminal_status.strip().lower()
        if not key or key in {RunLifecycleStatus.RUNNING.value, "running"}:
            return None
        if key == "error":
            return {"status": "failed"}
        try:
            RunLifecycleStatus(key)
        except ValueError:
            return None
        mapped = self._map_status(terminal_status)
        if mapped == "running":
            return None
        if mapped in {"completed", "failed", "canceled", "awaiting_human"}:
            return {"status": mapped}
        return None

    @staticmethod
    def _frame(seq: int, event: str, data: dict[str, Any]) -> bytes:
        payload = json.dumps(data, ensure_ascii=False, default=str)
        return f"id: {seq}\nevent: {event}\ndata: {payload}\n\n".encode()

    @staticmethod
    def _map_status(status: str) -> str:
        """归一化终态事件 status 到 LobeHub UI ``done`` 帧词表。"""
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
        if key in {RunLifecycleStatus.RUNNING.value, "running"}:
            return "running"
        if key in {RunLifecycleStatus.COMPLETED.value}:
            return "completed"
        if key in {RunLifecycleStatus.TIMEOUT.value, "timeout"}:
            return "failed"
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
        collected: dict[str, Any] = dict(getattr(event, "arguments", {}) or {})
        files = getattr(event, "files", None)
        if files and "files" not in collected:
            collected["files"] = list(files)
        return collected

    @staticmethod
    def _extract_arguments(event: Any) -> str:
        collected: dict[str, Any] = dict(getattr(event, "arguments", {}) or {})
        return json.dumps(collected, ensure_ascii=False, default=str)


__all__ = ["RunUiEncoder"]
