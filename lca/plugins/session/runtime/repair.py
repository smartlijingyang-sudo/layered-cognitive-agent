"""Crash-recovery repair for interrupted session turns (DSH interruptedTurnClosers).

Aligns with deepseek-harness ``packages/core/session/src/repair.ts``. Pure fold
over append-only facts; synthetic closers are appended only on cold load
(see :func:`repair_interrupted_turn`).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from lca.contracts.harness.tasks.session import SessionEvent
from lca_kernel.events.fold import SURFACE_ASSISTANT_TYPE, SURFACE_TOOL_RESULT_TYPE

__all__ = [
    "TOOL_NOT_STARTED",
    "TOOL_OUTCOME_UNKNOWN",
    "SessionRepairError",
    "repair_interrupted_turn",
]

TOOL_NOT_STARTED: str = "TOOL_NOT_STARTED"
"""Recovery code for an assistant tool request that never reached a recorded call."""

TOOL_OUTCOME_UNKNOWN: str = "TOOL_OUTCOME_UNKNOWN"
"""Recovery code for a recorded tool call whose outcome was not durably recorded."""

_TURN_START = frozenset({"turn.started.v1", "turn/start"})
_TURN_END = frozenset({"turn.ended.v1", "turn/end"})
_STEP_START = frozenset({"step.started.v1", "step/start"})
_STEP_END = frozenset({"step.ended.v1", "step/end"})
_ASSISTANT = frozenset(
    {
        SURFACE_ASSISTANT_TYPE,
        "assistant.responded.v1",
        "assistant/message",
    }
)
_TOOL_CALL = frozenset({"tool/call", "spine.phase.tool.call.start", "phase.tool.call.start"})
_TOOL_RESULT = frozenset(
    {
        SURFACE_TOOL_RESULT_TYPE,
        "tool/result",
        "body.tool.execute.end",
    }
)

_TOOL_NOT_STARTED_TEXT = (
    "The tool call was interrupted before the Harness recorded it as started. "
    "Retry it if it is still needed."
)
_TOOL_OUTCOME_UNKNOWN_TEXT = (
    "The tool call was interrupted after it was recorded, but no result was durably "
    "recorded. Its outcome is unknown. Decide whether to retry from the tool semantics: "
    "retry only if the operation is read-only or idempotent; if it may have side "
    "effects, first verify external state or ask the user. Do not retry blindly."
)


class SessionRepairError(ValueError):
    """Repair refused or input log cannot be closed safely."""


@dataclass
class _PendingCall:
    step: int
    call_seq: int | None = None
    tool_name: str = "unknown"


def repair_interrupted_turn(
    events: Sequence[SessionEvent],
    *,
    cold_load: bool = True,
) -> list[SessionEvent]:
    """Return synthetic closer events for an open tail turn.

    Scans ``events`` for a turn without ``turn.ended.v1`` / ``turn/end``, closes
    unmatched tool calls, then synthesizes ``step.ended.v1`` and ``turn.ended.v1``
    with reason ``interrupted``. Returns an empty list when the log is balanced.

    Live sessions must not receive synthetic repair (ADR-0191 §7.2): pass
    ``cold_load=False`` to fail closed instead of mutating facts.
    """
    open_turn: int | None = None
    open_step: int | None = None
    pending_calls: dict[str, _PendingCall] = {}

    for event in events:
        event_type = event.type
        data = event.data

        if event_type in _TURN_START:
            open_turn = _coerce_turn(data)
            open_step = None
            pending_calls.clear()
            continue

        if event_type in _TURN_END:
            open_turn = None
            open_step = None
            pending_calls.clear()
            continue

        if event_type in _STEP_START:
            open_step = _coerce_step(data)
            continue

        if event_type in _STEP_END:
            pending_calls.clear()
            open_step = None
            continue

        if event_type in _ASSISTANT:
            step = _coerce_step(data)
            for call_id, tool_name in _extract_assistant_tool_calls(data):
                pending_calls[call_id] = _PendingCall(step=step, tool_name=tool_name)
            continue

        if event_type in _TOOL_CALL:
            call_id = _extract_tool_call_id(data)
            if call_id is not None:
                entry = pending_calls.get(call_id)
                if entry is not None:
                    entry.call_seq = event.seq
            continue

        if event_type in _TOOL_RESULT:
            call_id = _extract_tool_result_call_id(data)
            if call_id is not None:
                pending_calls.pop(call_id, None)

    if not events or open_turn is None:
        return []

    if not cold_load:
        raise SessionRepairError(
            "refusing synthetic repair on live session with open turn (cold load only)"
        )

    last = events[-1]
    seq = last.seq + 1
    time = last.time
    session_id = last.session_id
    closers: list[SessionEvent] = []

    for call_id, pending in pending_calls.items():
        started = pending.call_seq is not None
        code = TOOL_OUTCOME_UNKNOWN if started else TOOL_NOT_STARTED
        error_name = "ToolOutcomeUnknownError" if started else "ToolNotStartedError"
        text = _TOOL_OUTCOME_UNKNOWN_TEXT if started else _TOOL_NOT_STARTED_TEXT
        closers.append(
            SessionEvent(
                type=SURFACE_TOOL_RESULT_TYPE,
                seq=seq,
                time=time,
                data={
                    "turn": open_turn,
                    "step": pending.step,
                    "tool_name": pending.tool_name,
                    "invocation_id": call_id,
                    "outcome": "error",
                    "message": {
                        "id": f"interrupted-tool-result-{call_id}-{seq}",
                        "role": "user",
                        "source": {"kind": "tool", "callId": call_id},
                        "content": [
                            {
                                "type": "tool-result",
                                "toolCallId": call_id,
                                "isError": True,
                                "content": [{"type": "text", "text": text}],
                            }
                        ],
                    },
                    "error": {"name": error_name, "code": code},
                },
                session_id=session_id,
                surface_op="append",
                source_event_seqs=(pending.call_seq,) if started else None,
            )
        )
        seq += 1

    if open_step is not None:
        closers.append(
            SessionEvent(
                type="step.ended.v1",
                seq=seq,
                time=time,
                data={"turn": open_turn, "step": open_step},
                session_id=session_id,
            )
        )
        seq += 1

    closers.append(
        SessionEvent(
            type="turn.ended.v1",
            seq=seq,
            time=time,
            data={"turn": open_turn, "reason": "interrupted"},
            session_id=session_id,
        )
    )
    return closers


def _coerce_turn(data: Mapping[str, Any]) -> int:
    value = data.get("turn")
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise SessionRepairError("turn coordinate must be a non-negative integer")
    return value


def _coerce_step(data: Mapping[str, Any]) -> int:
    value = data.get("step")
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise SessionRepairError("step coordinate must be a non-negative integer")
    return value


def _extract_assistant_tool_calls(data: Mapping[str, Any]) -> list[tuple[str, str]]:
    """Collect pending tool-call ids from assistant surface or compat events."""
    found: list[tuple[str, str]] = []

    message = data.get("message")
    if isinstance(message, Mapping):
        content = message.get("content")
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, Mapping):
                    continue
                if block.get("type") == "tool-call":
                    call_id = _stringify_call_id(block.get("id"))
                    if call_id is not None:
                        found.append((call_id, str(block.get("name") or "unknown")))
        return found

    tool_calls = data.get("tool_calls")
    if isinstance(tool_calls, list):
        for entry in tool_calls:
            if not isinstance(entry, Mapping):
                continue
            call_id = _stringify_call_id(entry.get("id") or entry.get("toolCallId"))
            if call_id is None:
                continue
            name = entry.get("name")
            if not isinstance(name, str):
                function = entry.get("function")
                if isinstance(function, Mapping):
                    name = function.get("name")
            found.append((call_id, str(name or "unknown")))
    return found


def _extract_tool_call_id(data: Mapping[str, Any]) -> str | None:
    for key in ("callId", "call_id", "invocation_id", "tool_call_id"):
        call_id = _stringify_call_id(data.get(key))
        if call_id is not None:
            return call_id
    payload = data.get("payload")
    if isinstance(payload, Mapping):
        return _extract_tool_call_id(payload)
    return None


def _extract_tool_result_call_id(data: Mapping[str, Any]) -> str | None:
    message = data.get("message")
    if isinstance(message, Mapping):
        source = message.get("source")
        if isinstance(source, Mapping):
            call_id = _stringify_call_id(source.get("callId") or source.get("call_id"))
            if call_id is not None:
                return call_id
        content = message.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, Mapping) and block.get("type") == "tool-result":
                    call_id = _stringify_call_id(block.get("toolCallId"))
                    if call_id is not None:
                        return call_id
    for key in ("invocation_id", "callId", "call_id", "tool_call_id"):
        call_id = _stringify_call_id(data.get(key))
        if call_id is not None:
            return call_id
    return None


def _stringify_call_id(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None
