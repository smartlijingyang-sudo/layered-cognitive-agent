"""Cursor phase-window advance wrapper (ADR-0185 P5).

This module now only handles cursor phase-window advance; fact-write methods
have been retired (ADR-0185 P5).  The business path routes through
``lca.loop.commit.tool_journal.record_step_tool_call`` /
``record_step_tool_result`` — single track via FactGateway → Session.append.
"""

from __future__ import annotations

import structlog

from lca.contracts.observability.cursor.loop_cursor import CursorError, LoopCursor, PhaseName

_log = structlog.get_logger(__name__)


class CursorRecord:
    """Phase-window advance wrapper (demoted by ADR-0185 P5).

    Fact-write methods (``try_record_tool_call`` / ``try_record_tool_result``)
    have been retired.  Only ``get()`` and ``try_advance()`` remain.
    """

    @staticmethod
    def get() -> LoopCursor | None:
        """Return the currently bound cursor, or ``None`` when no spine is wired."""
        from lca.infrastructure.observability.loop_cursor.coordinator.adapter import (
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


__all__ = ["CursorRecord"]
