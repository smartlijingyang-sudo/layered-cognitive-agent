"""SSOT for cursor.record_* writes (R2).

Replaces 7+ duplicated ``try/except CursorError → warning`` blocks across body
and tool-executor modules. The lazy import of ``get_current_cursor`` lives
here only.
"""

from __future__ import annotations

from typing import Any, Literal

import structlog

from lca.contracts.observability.loop_cursor import CursorError, LoopCursor, PhaseName

_log = structlog.get_logger(__name__)


class CursorRecord:
    """Best-effort ``cursor.record_*`` writer (R2 consolidation).

    Cursor writes are advisory evidence; a missing cursor (no run context) or a
    phase-guard rejection (``CursorError``) must not escalate to a session-level
    RuntimeError (ADR-0169 PR-26 task-25, run_b61bb9ed5707 root cause).

    **2026-09-03 观测面 SSOT 收口**(根 note `observation-ssot-registry`):
    ``step.tool_call.record`` / ``step.tool_result.record`` 的 payload 必须
    携带调用 / 结果的全部结构化字段(``invocation_id`` / ``arguments`` /
    ``arguments_summary`` / ``ok`` / ``latency_ms`` / ``stdout_head`` /
    ``stderr`` / ``files_created`` / ``error`` / ``delta_summary``),而非
    仅 ``tool_name`` + digest。``CursorRecord`` 作为唯一 writer 入口,
    负责把这些字段全部透传给 ``cursor.record_tool_call`` /
    ``cursor.record_tool_result``(后者在 std.py 已支持 kwargs 透传,
    这条路在 PR-26 task-25 之前被错误地走了一个简化的 dataclass-only
    入口,导致 deriver 永远看不到调用内容 —— Bug #1 根因)。
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
        arguments: dict[str, Any] | None = None,
        arguments_summary: str = "",
    ) -> None:
        """Write one ``step.tool_call.record`` EP via the bound cursor (best-effort).

        ``arguments`` / ``arguments_summary`` 由 caller 实际掌握
        (safe_executor._execute / tool_journal_emit._summarize_args 已经
        在手),必须透传给 cursor,而不是仅发 digest 占位。这样:

        - step_tree deriver 在没做 sidecar round-trip 的情况下也能拿到
          tool 调用内容;
        - exceptions.jsonl / journal.json / model_visible 三处对 tool
          调用的还原走同一条字段链,无需 reader 自己 parse digest。
        """
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
                ),
                arguments=arguments or {},
                arguments_summary=arguments_summary,
                invocation_id=invocation_id,
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
        invocation_id: str = "",
        ok: bool = True,
        latency_ms: int = 0,
        stdout_head: str = "",
        stdout_chars_total: int = 0,
        stdout_truncated: bool = False,
        stderr: str = "",
        files_created: tuple[str, ...] = (),
        error: str | None = None,
        delta_summary: str = "",
    ) -> None:
        """Write one ``step.tool_result.record`` EP via the bound cursor (best-effort).

        所有 caller 已知字段全部透传。``delta_summary`` 兜底 —— caller
        没传时由 ``result_digest`` 取代(同语义,只是人话 vs fingerprint)。
        """
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
                ),
                invocation_id=invocation_id,
                ok=ok,
                latency_ms=latency_ms,
                stdout_head=stdout_head,
                stdout_chars_total=stdout_chars_total,
                stdout_truncated=stdout_truncated,
                stderr=stderr,
                files_created=files_created,
                error=error,
                delta_summary=delta_summary,
            )
        except CursorError as exc:
            _log.warning(
                "cursor_record_tool_result_failed",
                tool_name=tool_name,
                current_phase=cursor.snapshot.phase,
                error=str(exc),
            )


__all__ = ["CursorRecord"]
