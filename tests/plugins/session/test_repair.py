"""Session crash-repair tests (ADR-0191 Wave B1 / I-RESUME-1..2).

Pure-function coverage aligned with deepseek-harness
``packages/core/session/tests/repair.spec.ts``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lca.contracts.harness.tasks.session import SessionEvent
from lca.plugins.session.runtime.repair import (
    TOOL_NOT_STARTED,
    TOOL_OUTCOME_UNKNOWN,
    SessionRepairError,
    repair_interrupted_turn,
)
from lca.plugins.session.runtime.store import SessionStore
from lca_kernel.events.fold import SURFACE_ASSISTANT_TYPE, SURFACE_TOOL_RESULT_TYPE
from lca_kernel.events.session import SESSION_FORMAT_VERSION, SessionHeader

_SESSION = "repair-test"


def _event(
    seq: int,
    event_type: str,
    data: dict,
    *,
    time: int | None = None,
    surface_op: str | None = None,
    source_event_seqs: tuple[int, ...] | None = None,
) -> SessionEvent:
    return SessionEvent(
        type=event_type,
        seq=seq,
        time=time if time is not None else seq,
        data=data,
        session_id=_SESSION,
        surface_op=surface_op,
        source_event_seqs=source_event_seqs,
    )


def _turn_start(turn: int, seq: int) -> SessionEvent:
    return _event(seq, "turn.started.v1", {"turn": turn})


def _turn_end(turn: int, seq: int, *, reason: str = "completed") -> SessionEvent:
    return _event(seq, "turn.ended.v1", {"turn": turn, "reason": reason})


def _step_start(turn: int, step: int, seq: int) -> SessionEvent:
    return _event(seq, "step.started.v1", {"turn": turn, "step": step})


def _step_end(turn: int, step: int, seq: int) -> SessionEvent:
    return _event(seq, "step.ended.v1", {"turn": turn, "step": step})


def _assistant_with_tool_call(
    turn: int,
    step: int,
    seq: int,
    call_id: str,
    *,
    tool_name: str = "bash",
) -> SessionEvent:
    return _event(
        seq,
        SURFACE_ASSISTANT_TYPE,
        {
            "turn": turn,
            "step": step,
            "step_id": f"t{turn}s{step}",
            "incarnation": 1,
            "assistant_content": "calling a tool",
            "tool_calls": [{"id": call_id, "name": tool_name, "arguments": "{}"}],
            "finish_reason": "tool_calls",
            "usage": {"prompt_tokens": 0, "completion_tokens": 0},
            "header_digest": "digest",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "calling a tool"},
                    {
                        "type": "tool-call",
                        "id": call_id,
                        "name": tool_name,
                        "arguments": "{}",
                    },
                ],
            },
        },
        surface_op="append",
    )


def _tool_call(turn: int, step: int, seq: int, call_id: str) -> SessionEvent:
    return _event(
        seq,
        "tool/call",
        {
            "turn": turn,
            "step": step,
            "callId": call_id,
            "name": "bash",
            "arguments": "{}",
        },
    )


def _tool_result(turn: int, step: int, seq: int, call_id: str) -> SessionEvent:
    return _event(
        seq,
        SURFACE_TOOL_RESULT_TYPE,
        {
            "turn": turn,
            "step": step,
            "invocation_id": call_id,
            "outcome": "success",
            "message": {
                "role": "user",
                "source": {"kind": "tool", "callId": call_id},
                "content": [
                    {
                        "type": "tool-result",
                        "toolCallId": call_id,
                        "isError": False,
                        "content": [{"type": "text", "text": "ok"}],
                    }
                ],
            },
        },
        surface_op="append",
    )


def _types(closers: list[SessionEvent]) -> list[str]:
    return [event.type for event in closers]


def _seqs(closers: list[SessionEvent]) -> list[int]:
    return [event.seq for event in closers]


class TestRepairInterruptedTurn:
    def test_balanced_log_returns_empty(self) -> None:
        events = [_turn_start(1, 0), _turn_end(1, 1)]
        assert repair_interrupted_turn(events) == []

    def test_empty_log_returns_empty(self) -> None:
        assert repair_interrupted_turn([]) == []

    def test_open_turn_only_closes_turn(self) -> None:
        closers = repair_interrupted_turn([_turn_start(1, 0)])
        assert _types(closers) == ["turn.ended.v1"]
        assert closers[0].seq == 1
        assert closers[0].data["reason"] == "interrupted"

    def test_open_step_closes_step_then_turn(self) -> None:
        events = [_turn_start(1, 0), _step_start(1, 1, 1)]
        closers = repair_interrupted_turn(events)
        assert _types(closers) == ["step.ended.v1", "turn.ended.v1"]
        assert _seqs(closers) == [2, 3]

    def test_unstarted_tool_call_gets_not_started_result(self) -> None:
        events = [
            _turn_start(2, 0),
            _step_start(2, 1, 1),
            _assistant_with_tool_call(2, 1, 2, "call-1"),
        ]
        closers = repair_interrupted_turn(events)
        assert _types(closers) == [
            SURFACE_TOOL_RESULT_TYPE,
            "step.ended.v1",
            "turn.ended.v1",
        ]
        assert _seqs(closers) == [3, 4, 5]
        result = closers[0]
        assert result.data["error"] == {"name": "ToolNotStartedError", "code": TOOL_NOT_STARTED}
        text = result.data["message"]["content"][0]["content"][0]["text"]
        assert "before the Harness recorded it as started" in text

    def test_answered_tool_call_skips_synthetic_result(self) -> None:
        events = [
            _turn_start(2, 0),
            _step_start(2, 1, 1),
            _assistant_with_tool_call(2, 1, 2, "call-1"),
            _tool_result(2, 1, 3, "call-1"),
        ]
        closers = repair_interrupted_turn(events)
        assert _types(closers) == ["step.ended.v1", "turn.ended.v1"]

    def test_closed_step_skips_synthetic_result(self) -> None:
        events = [
            _turn_start(2, 0),
            _step_start(2, 1, 1),
            _assistant_with_tool_call(2, 1, 2, "call-1"),
            _step_end(2, 1, 3),
        ]
        closers = repair_interrupted_turn(events)
        assert _types(closers) == ["turn.ended.v1"]
        assert closers[0].seq == 4

    def test_only_open_turn_gets_repair(self) -> None:
        events = [
            _turn_start(1, 0),
            _step_start(1, 1, 1),
            _assistant_with_tool_call(1, 1, 2, "old-call"),
            _tool_result(1, 1, 3, "old-call"),
            _step_end(1, 1, 4),
            _turn_end(1, 5),
            _turn_start(2, 6),
            _step_start(2, 1, 7),
            _assistant_with_tool_call(2, 1, 8, "new-call"),
        ]
        closers = repair_interrupted_turn(events)
        assert _types(closers) == [
            SURFACE_TOOL_RESULT_TYPE,
            "step.ended.v1",
            "turn.ended.v1",
        ]
        assert closers[0].data["invocation_id"] == "new-call"

    def test_multiple_unanswered_calls_preserve_order(self) -> None:
        events = [
            _turn_start(1, 0),
            _step_start(1, 1, 1),
            _assistant_with_tool_call(1, 1, 2, "call-a"),
            _tool_result(1, 1, 3, "call-a"),
            _event(
                4,
                SURFACE_ASSISTANT_TYPE,
                {
                    "turn": 1,
                    "step": 1,
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool-call",
                                "id": "call-b",
                                "name": "bash",
                                "arguments": "{}",
                            }
                        ],
                    },
                },
                surface_op="append",
            ),
        ]
        closers = repair_interrupted_turn(events)
        assert _types(closers) == [
            SURFACE_TOOL_RESULT_TYPE,
            "step.ended.v1",
            "turn.ended.v1",
        ]
        assert closers[0].data["invocation_id"] == "call-b"

    def test_started_tool_call_gets_outcome_unknown(self) -> None:
        events = [
            _turn_start(1, 0),
            _step_start(1, 1, 1),
            _assistant_with_tool_call(1, 1, 2, "call-1"),
            _tool_call(1, 1, 3, "call-1"),
        ]
        closers = repair_interrupted_turn(events)
        result = closers[0]
        assert result.surface_op == "append"
        assert result.source_event_seqs == (3,)
        assert result.data["error"] == {
            "name": "ToolOutcomeUnknownError",
            "code": TOOL_OUTCOME_UNKNOWN,
        }
        text = result.data["message"]["content"][0]["content"][0]["text"]
        assert "read-only or idempotent" in text

    def test_orphan_tool_call_without_assistant_does_not_synthesize_result(self) -> None:
        events = [
            _turn_start(1, 0),
            _step_start(1, 1, 1),
            _tool_call(1, 1, 2, "orphan"),
        ]
        closers = repair_interrupted_turn(events)
        assert _types(closers) == ["step.ended.v1", "turn.ended.v1"]

    def test_live_open_turn_rejects_cold_repair(self) -> None:
        events = [_turn_start(1, 0), _step_start(1, 1, 1)]
        with pytest.raises(SessionRepairError, match="live session"):
            repair_interrupted_turn(events, cold_load=False)

    def test_assistant_responded_compat_tool_calls(self) -> None:
        events = [
            _turn_start(1, 0),
            _step_start(1, 1, 1),
            _event(
                2,
                "assistant.responded.v1",
                {
                    "turn": 1,
                    "step": 1,
                    "content": "run tool",
                    "tool_calls": [{"id": "tc-1", "name": "grep", "arguments": "{}"}],
                },
            ),
        ]
        closers = repair_interrupted_turn(events)
        assert closers[0].data["invocation_id"] == "tc-1"
        assert closers[0].data["tool_name"] == "grep"


class TestRestoreIntegration:
    def test_restore_from_log_applies_repair_closers(self, tmp_path: Path) -> None:
        session_id = "repaired-run"
        path = tmp_path / f"{session_id}.spine.jsonl"
        path.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "type": "turn.started.v1",
                            "seq": 0,
                            "time": 1,
                            "data": {"turn": 1},
                        }
                    ),
                    json.dumps(
                        {
                            "type": "step.started.v1",
                            "seq": 1,
                            "time": 2,
                            "data": {"turn": 1, "step": 1},
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        store = SessionStore()
        header = SessionHeader(version=SESSION_FORMAT_VERSION, id=session_id, created_at=9000)
        session = store.restore_from_log(session_id, header, path)
        assert session.seq == 4
        types = [event.type for event in session.snapshot_events()]
        assert types == [
            "turn.started.v1",
            "step.started.v1",
            "step.ended.v1",
            "turn.ended.v1",
        ]
        assert session.snapshot_events()[-1].data["reason"] == "interrupted"
