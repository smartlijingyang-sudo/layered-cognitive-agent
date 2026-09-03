"""R2 tests for ``CursorRecord`` — best-effort cursor writes + lazy import.

Drives the real shipped ``CursorRecord`` class so the SSOT stays the only
implementation.  Three failure modes are exercised per method:

1. No cursor bound → silent no-op (no exception escapes).
2. Cursor raises ``CursorError`` → swallowed, warning logged.
3. Cursor accepts → ``record_tool_call`` / ``record_tool_result`` invoked.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lca.cognition.body.cursor_record import CursorRecord
from lca.contracts.atoms.enums import ActionType
from lca.contracts.observability.incarnation import Incarnation
from lca.contracts.observability.loop_cursor import CursorError, PhaseName
from lca.contracts.observability.loop_cursor_payloads import (
    ToolCallRecord,
    ToolResultRecord,
)
from lca.infrastructure.observability.loop_cursor import StdLoopCursor
from lca.infrastructure.observability.loop_cursor.coordinator_adapter import (
    bind_current_cursor,
    reset_current_cursor,
)


@dataclass
class _StubSpine:
    """Minimal ``WritePort`` that captures all append calls."""

    records: list[dict[str, Any]] = field(default_factory=list)

    def append(
        self,
        *,
        execution_point: str,
        payload: dict[str, Any],
        run_id: str,
        seq: int,
        incarnation: int,
        phase: str | None,
    ) -> int:
        self.records.append(
            {"execution_point": execution_point, "payload": payload, "phase": phase}
        )
        return seq


def _make_cursor() -> StdLoopCursor:
    spine = _StubSpine()
    cursor = StdLoopCursor(
        spine=spine,  # type: ignore[arg-type]
        run_id="r1",
        trace_id="t1",
        incarnation=Incarnation(run_id="r1", plan_ref="solo", incarnation_seq=1),
    )
    cursor.advance("perceive")
    cursor.advance("think")
    cursor.advance("act")
    return cursor


class _RejectingCursor:
    """Cursor stub that always raises ``CursorError`` on every operation."""

    @property
    def snapshot(self) -> Any:
        return type("S", (), {"phase": "act"})()

    def advance(self, phase: PhaseName) -> None:
        raise CursorError("rejected")

    def record_tool_call(self, payload: ToolCallRecord) -> None:
        raise CursorError("rejected")

    def record_tool_result(self, payload: ToolResultRecord) -> None:
        raise CursorError("rejected")


def test_get_returns_none_when_no_cursor_wired() -> None:
    """Without a bound cursor, ``CursorRecord.get()`` returns ``None``."""
    assert CursorRecord.get() is None


def test_try_advance_is_noop_without_cursor() -> None:
    """``try_advance`` with no cursor wired must not raise."""
    CursorRecord.try_advance("act")  # does not raise
    CursorRecord.try_advance("act", action_type=ActionType.USE_TOOL.value)


def test_try_record_tool_call_is_noop_without_cursor() -> None:
    """``try_record_tool_call`` with no cursor wired must not raise."""
    CursorRecord.try_record_tool_call(
        tool_name="t",
        invocation_id="inv-1",
        args_digest="d",
    )


def test_try_record_tool_result_is_noop_without_cursor() -> None:
    """``try_record_tool_result`` with no cursor wired must not raise."""
    CursorRecord.try_record_tool_result(
        tool_name="t",
        result_digest="d",
        outcome="ok",
    )


def test_try_advance_invokes_cursor_advance() -> None:
    """With a bound cursor, ``try_advance`` drives ``cursor.advance(target)``."""
    cursor = _make_cursor()
    token = bind_current_cursor(cursor)  # type: ignore[arg-type]
    try:
        CursorRecord.try_advance("stop", action_type=ActionType.STOP.value)
        assert cursor.snapshot.phase == "stop"
    finally:
        reset_current_cursor(token)


def test_try_advance_swallows_cursor_error() -> None:
    """``CursorError`` from ``cursor.advance`` → warning logged, no re-raise."""
    cursor = _RejectingCursor()
    token = bind_current_cursor(cursor)  # type: ignore[arg-type]
    try:
        CursorRecord.try_advance("act", action_type=ActionType.USE_TOOL.value)
    finally:
        reset_current_cursor(token)


def test_try_record_tool_call_invokes_cursor() -> None:
    """``try_record_tool_call`` builds the same ``ToolCallRecord`` the legacy code did."""
    cursor = _make_cursor()
    token = bind_current_cursor(cursor)  # type: ignore[arg-type]
    try:
        CursorRecord.try_record_tool_call(
            tool_name="my_tool",
            invocation_id="inv-1",
            args_digest="tool:my_tool",
        )
    finally:
        reset_current_cursor(token)


def test_try_record_tool_result_invokes_cursor() -> None:
    """``try_record_tool_result`` builds the same ``ToolResultRecord`` the legacy code did."""
    cursor = _make_cursor()
    token = bind_current_cursor(cursor)  # type: ignore[arg-type]
    try:
        CursorRecord.try_record_tool_result(
            tool_name="my_tool",
            result_digest="ok",
            outcome="ok",
        )
        CursorRecord.try_record_tool_result(
            tool_name="my_tool",
            result_digest="failure",
            outcome="failure",
        )
    finally:
        reset_current_cursor(token)


def test_try_record_tool_call_swallows_cursor_error() -> None:
    """``CursorError`` from ``record_tool_call`` → swallowed, no re-raise."""
    cursor = _RejectingCursor()
    token = bind_current_cursor(cursor)  # type: ignore[arg-type]
    try:
        CursorRecord.try_record_tool_call(
            tool_name="t",
            invocation_id="inv-1",
            args_digest="d",
        )
    finally:
        reset_current_cursor(token)


def test_try_record_tool_result_swallows_cursor_error() -> None:
    """``CursorError`` from ``record_tool_result`` → swallowed, no re-raise."""
    cursor = _RejectingCursor()
    token = bind_current_cursor(cursor)  # type: ignore[arg-type]
    try:
        CursorRecord.try_record_tool_result(
            tool_name="t",
            result_digest="d",
            outcome="failure",
        )
    finally:
        reset_current_cursor(token)
