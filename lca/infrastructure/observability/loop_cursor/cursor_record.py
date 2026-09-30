"""Cursor phase-window advance wrapper (ADR-0185 P5 + spec section H).

This module now only handles cursor phase-window advance; fact-write methods
have been retired (ADR-0185 P5). The business path routes through
``lca.loop.commit.tool_journal.record_step_tool_call`` /
``record_step_tool_result`` — single track via FactGateway → Session.append.

spec section H ContextVar deletion: cursor flows through explicit DI.
``CursorRecord`` exposes a class-level ``bind(cursor)`` to set the cursor
the instance operates on (callers wire it once at run-setup); ``get()``
returns the bound cursor or ``None``. No more ContextVar lookup.
"""

from __future__ import annotations

import structlog

from lca.contracts.observability.cursor.loop_cursor import CursorError, LoopCursor, PhaseName

_log = structlog.get_logger(__name__)


class CursorRecord:
    """Phase-window advance wrapper (demoted by ADR-0185 P5 + spec section H).

    Fact-write methods (``try_record_tool_call`` / ``try_record_tool_result``)
    have been retired. Only ``bind()`` / ``get()`` / ``try_advance()`` remain.
    """

    _cursor: LoopCursor | None = None

    @classmethod
    def bind(cls, cursor: LoopCursor | None) -> LoopCursor | None:
        """Bind a cursor (or ``None`` to clear) for this process.

        spec section H: replaces ``get_current_cursor()`` ContextVar lookup
        with explicit per-run binding at run-setup time. Returns the
        previously bound cursor (or ``None``) for callers that want to
        re-bind at resume.
        """
        previous = cls._cursor
        cls._cursor = cursor
        return previous

    @classmethod
    def get(cls) -> LoopCursor | None:
        """Return the currently bound cursor, or ``None`` when no spine is wired."""
        return cls._cursor

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
