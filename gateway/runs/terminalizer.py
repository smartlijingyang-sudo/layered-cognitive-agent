"""Coordinate the ordered terminal transition for one legacy Gateway run.

Terminal-state derivation, artifact closure, manifest materialization, and
exporter disposal have focused owners.  ``RunTerminalizer`` preserves the one
public sequencing point shared by initial execution and resume paths.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from gateway.runs.artifact_closure import (
    emit_artifact_closure_if_needed as _emit_artifact_closure_if_needed,
)
from gateway.runs.export_disposal import dispose_export as _dispose_export
from gateway.runs.session import RunRegistry, RunSession
from gateway.runs.terminal_materialization import (
    record_terminal_materialization as _record_terminal_materialization,
)
from gateway.runs.terminal_status import derive_terminal_status as _derive_terminal_status
from lca.layer0_infra.tools.run_finalizer import finalize_run

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


__all__ = ["RunTerminalizer"]
