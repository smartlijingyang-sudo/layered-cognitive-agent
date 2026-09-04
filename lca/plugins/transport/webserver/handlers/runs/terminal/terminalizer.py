"""Coordinate the ordered terminal transition for one legacy Gateway run.

Terminal-state derivation, artifact closure, manifest materialization, and
exporter disposal have focused owners.  ``RunTerminalizer`` preserves the one
public sequencing point shared by initial execution and resume paths.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from lca.infrastructure.tools.run_finalizer import finalize_run
from lca.plugins.transport.webserver.handlers.runs.lifecycle.export_disposal import (
    dispose_export as _dispose_export,
)
from lca.plugins.transport.webserver.handlers.runs.observability.artifact_closure import (
    emit_artifact_closure_if_needed as _emit_artifact_closure_if_needed,
)
from lca.plugins.transport.webserver.handlers.runs.session.session import RunRegistry, RunSession
from lca.plugins.transport.webserver.handlers.runs.terminal.materialization import (
    record_terminal_materialization as _record_terminal_materialization,
)
from lca.plugins.transport.webserver.handlers.runs.terminal.status import (
    derive_terminal_status as _derive_terminal_status,
)

_log = structlog.get_logger(__name__)


class RunTerminalizer:
    """Own the order from active run to materialized terminal state."""

    def __init__(
        self,
        registry: RunRegistry,
        *,
        finalizer: Callable[[str], Awaitable[None]] = finalize_run,
        materializer: Callable[[RunSession], None] | None = None,
    ) -> None:
        self._registry = registry
        self._finalizer = finalizer
        self._materializer = materializer or _record_terminal_materialization

    async def terminalize(self, session: RunSession, *, workspace: Any, success: bool) -> None:
        """Close a run exactly once while preserving Journal ownership of terminal facts."""
        # ADR-0169 PR-12.7:close reason 由 terminal outcome 派生 — 'completed' 为
        # 成功,'error' 为异常失败,与 cursor.close / LoopCursor 契约语义对齐。
        from lca.contracts.observability.close_barrier import CloseReason

        close_reason: CloseReason = "completed" if success else "error"
        try:
            if session.hub is not None:
                _emit_artifact_closure_if_needed(workspace, session, session.hub)
            await self._finalizer(session.run_id)
        except Exception:
            _log.exception("finalize_run_pre_close_failed", hop="H2", run_id=session.run_id)
        finally:
            try:
                if session.hub is not None:
                    session.hub.close()
            finally:
                _derive_terminal_status(session, success)
                self._registry.clear_inflight(session.run_id)
                self._registry.prune()
                self._materializer(session)
                if session.hub is not None:
                    await _dispose_export(session.hub)
                # ADR-0169 PR-12.7:释放 loop_cursor ContextVar token
                # (单进程 leak 修复点);close 内部幂等,
                # 二重调用不再 reset(terminalizer 行为不受影响)。
                try:
                    released = session.close(close_reason)
                    if not released:
                        _log.debug(
                            "run_session_already_closed",
                            run_id=session.run_id,
                        )
                except Exception:
                    _log.exception(
                        "run_session_close_token_reset_failed",
                        run_id=session.run_id,
                    )


__all__ = ["RunTerminalizer"]
