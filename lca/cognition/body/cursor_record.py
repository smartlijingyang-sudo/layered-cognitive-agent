"""SSOT for cursor.record_* writes (R2).

Replaces 7+ duplicated ``try/except CursorError → warning`` blocks across body
and tool-executor modules. The lazy import of ``get_current_cursor`` lives
here only.
"""

from __future__ import annotations

from typing import Literal

import structlog

from lca.contracts.observability.loop_cursor import CursorError, LoopCursor, PhaseName

_log = structlog.get_logger(__name__)


class CursorRecord:
    """Best-effort ``cursor.record_*`` writer (R2 consolidation).

    Cursor writes are advisory evidence; a missing cursor (no run context) or a
    phase-guard rejection (``CursorError``) must not escalate to a session-level
    RuntimeError (ADR-0169 PR-26 task-25, run_b61bb9ed5707 root cause).
    """

    @staticmethod
    def get() -> LoopCursor | None:
        """Return the currently bound cursor, or ``None`` when no spine is wired."""
        from lca.infrastructure.observability.loop_cursor.coordinator_adapter import (
            get_current_cursor,
        )

        return get_current_cursor()

    @staticmethod
    def try_advance(target: PhaseName, *, action_type: str | None = None) -> None:
        """Advance cursor to ``target``; silent no-op when no cursor is bound.

        ``CursorError`` is logged at warning level and swallowed so a single
        advance failure does not surface as a session RuntimeError.
        """
        cursor = CursorRecord.get()
        if cursor is None:
            return
        try:
            cursor.advance(target)
        except CursorError as exc:
            _log.warning(
                "body_advance_cursor_failed",
                action_type=action_type,
                target_phase=target,
                current_phase=cursor.snapshot.phase,
                error=str(exc),
            )

    @staticmethod
    def try_record_tool_call(
        *,
        tool_name: str,
        invocation_id: str,
        args_digest: str,
    ) -> None:
        """Write one ``step.tool_call.record`` EP via the bound cursor (best-effort)."""
        from lca.contracts.observability.loop_cursor_payloads import ToolCallRecord

        cursor = CursorRecord.get()
        if cursor is None:
            return
        try:
            cursor.record_tool_call(
                ToolCallRecord(
                    tool_name=tool_name,
                    args_digest=args_digest,
                    args_payload_path=None,
                    call_seq=hash(invocation_id) & 0x7FFFFFFF,
                )
            )
        except CursorError as exc:
            _log.warning(
                "cursor_record_tool_call_failed",
                tool_name=tool_name,
                invocation_id=invocation_id,
                current_phase=cursor.snapshot.phase,
                error=str(exc),
            )

    @staticmethod
    def try_record_tool_result(
        *,
        tool_name: str,
        result_digest: str | None,
        outcome: Literal["ok", "failure", "timeout", "denied"],
    ) -> None:
        """Write one ``step.tool_result.record`` EP via the bound cursor (best-effort)."""
        from lca.contracts.observability.loop_cursor_payloads import ToolResultRecord

        cursor = CursorRecord.get()
        if cursor is None:
            return
        try:
            cursor.record_tool_result(
                ToolResultRecord(
                    tool_name=tool_name,
                    result_digest=result_digest or "",
                    result_path=None,
                    outcome=outcome,
                )
            )
        except CursorError as exc:
            _log.warning(
                "cursor_record_tool_result_failed",
                tool_name=tool_name,
                current_phase=cursor.snapshot.phase,
                error=str(exc),
            )


__all__ = ["CursorRecord"]
