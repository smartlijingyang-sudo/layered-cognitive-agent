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

import pytest

from lca.cognition.body.executor.cursor_record import CursorRecord
from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.observability.core.incarnation import Incarnation
from lca.contracts.observability.cursor.loop_cursor import CursorError, PhaseName
from lca.contracts.observability.cursor.loop_cursor_payloads import (
    ToolCallRecord,
    ToolResultRecord,
)
from lca.infrastructure.observability.loop_cursor import StdLoopCursor
from lca.infrastructure.observability.loop_cursor.coordinator.adapter import (
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

    def record_tool_call(self, payload: ToolCallRecord, **kwargs: Any) -> None:
        raise CursorError("rejected")

    def record_tool_result(self, payload: ToolResultRecord, **kwargs: Any) -> None:
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
        ok=True,
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
            ok=True,
        )
        CursorRecord.try_record_tool_result(
            tool_name="my_tool",
            result_digest="failure",
            outcome="failure",
            ok=False,
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
            ok=False,
        )
    finally:
        reset_current_cursor(token)


# ── 回归锁 run_1f5360d2fa47:ok/outcome 必须显式 + 矛盾拒绝 ────────────────────


def test_try_record_tool_result_rejects_outcome_failure_without_ok_false() -> None:
    """``outcome="failure"`` 必须显式 ``ok=False``,否则抛 ValueError。

    防止上游(PipelineSafeExecutor 等)漏传 ok= 导致 ``ok=True`` 默认落地
    而 outcome 写为 failure 的矛盾样本 —— 这正是 run_1f5360d2fa47 的
    pdftotext exit_code=127 在 journal 中表现为 ok=True 的根因。
    """
    with pytest.raises(ValueError, match="tool_result contradiction"):
        CursorRecord.try_record_tool_result(
            tool_name="pdftotext",
            result_digest="exit_code=127",
            outcome="failure",
            ok=True,  # 故意错的,验证 invariant
        )


def test_try_record_tool_result_rejects_outcome_ok_without_ok_true() -> None:
    """``outcome="ok"`` 与 ``ok=False`` 矛盾 → ValueError。"""
    with pytest.raises(ValueError, match="tool_result contradiction"):
        CursorRecord.try_record_tool_result(
            tool_name="x",
            result_digest="",
            outcome="ok",
            ok=False,
        )


def test_try_record_tool_result_rejects_outcome_denied_with_ok_true() -> None:
    """``outcome="denied"`` 必须显式 ``ok=False``(tool_journal.py:201 修复锁)。"""
    with pytest.raises(ValueError, match="tool_result contradiction"):
        CursorRecord.try_record_tool_result(
            tool_name="x",
            result_digest="not in manifest",
            outcome="denied",
            ok=True,
        )


def test_tool_result_record_rejects_missing_ok() -> None:
    """``ToolResultRecord`` 类型层保证 ok 必填 —— 防止回归到 ``ok=True`` 默认。"""
    with pytest.raises(TypeError):
        ToolResultRecord(
            tool_name="t",
            result_digest="d",
            result_path=None,
            outcome="ok",
            # ok 故意省略
        )


def test_regression_run_1f5360d2fa47_failed_tool_propagates_ok_false() -> None:
    """回归锁:PipelineSafeExecutor-style 调用链下,failing 工具的 ok=False
    必须穿过 try_record_tool_result 抵达 cursor。"""
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
    token = bind_current_cursor(cursor)  # type: ignore[arg-type]
    try:
        # 模拟 pipeline_safe_executor.py:358 的失败分支
        CursorRecord.try_record_tool_result(
            tool_name="runCommand",
            result_digest="exit_code=127",
            outcome="failure",
            ok=False,
            error="sh: 1: pdftotext: not found",
        )
    finally:
        reset_current_cursor(token)
    last = spine.records[-1]
    assert last["execution_point"] == "step.tool_result.record"
    payload = last["payload"]
    assert payload["outcome"] == "failure"
    assert payload["ok"] is False
    assert "pdftotext" in payload["error"]
