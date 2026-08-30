"""Coordinate the legacy Gateway run environment in one explicit scope order.

Binding selection, attachment staging, and cognitive run-context projection live
in focused modules.  This coordinator owns only the order in which those pieces
enter carrier-side scopes before a loop driver executes.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, cast

import structlog

from gateway.runs.api.attachment_staging import (
    stage_machine_attachments as _stage_machine_attachments,
)
from gateway.runs.execute.environment_bindings import (
    resolve_bindings as _resolve_bindings,
)
from gateway.runs.execute.environment_bindings import (
    resolve_descriptor_registry as _resolve_descriptor_registry,
)
from gateway.runs.execute.environment_bindings import resolve_driver as _resolve_driver
from gateway.runs.execute.environment_bindings import (
    resolve_run_providers as _resolve_run_providers,
)
from gateway.runs.execute.loop_drivers import RunLoopDriver
from gateway.runs.lifecycle.run_context_factory import (
    run_context_for_session as _run_context_for_session,
)
from gateway.runs.session.session import RunSession
from lca.contracts.atoms.ids import RunId, TraceId
from lca.contracts.models.core.plane import PlaneBindings
from lca.contracts.models.observability.journal import RunScope
from lca.contracts.models.team.run_context import RunContext
from lca.contracts.protocols.runtime.infra import MachineResolver
from lca.infrastructure.observability import BoundObservability, bind_backends, run_scope
from lca.infrastructure.observability.event_descriptor_env import bind_descriptors
from lca.infrastructure.runtime_plane.scope import plane_bindings_scope
from lca.infrastructure.sandbox.runtime_scope import bind_sandbox_runtime
from lca.infrastructure.search.scope import search_run_scope
from lca.infrastructure.tools.run_attachment_scope import run_attachment_scope
from lca.infrastructure.tools.run_finalizer import run_id_scope
from lca.infrastructure.workspace import run_workspace_scope


@dataclass(frozen=True)
class PreparedRun:
    """Fully resolved inputs that a legacy loop driver may consume."""

    driver: RunLoopDriver
    bindings: PlaneBindings
    run_context: RunContext
    workspace: Any


class RunExecutionEnvironment:
    """Enter the carrier scopes that make one resolved legacy run executable."""

    def __init__(
        self,
        session: RunSession,
        *,
        ctx: Any,
        hub: BoundObservability,
        machine_resolver: MachineResolver | None = None,
    ) -> None:
        self._session = session
        self._ctx = ctx
        self._hub = hub
        self._machine_resolver = machine_resolver

    @asynccontextmanager
    async def prepare(self) -> AsyncIterator[PreparedRun]:
        """Yield a driver-ready environment after ordered carrier preflight."""
        session = self._session
        with (
            run_id_scope(session.run_id),
            run_attachment_scope(session.attachment_ids),
            run_workspace_scope(session.run_id) as workspace,
            search_run_scope(),
            run_scope(
                RunScope(
                    trace_id=cast("TraceId", session.trace_id),
                    run_id=cast("RunId", session.run_id),
                )
            ),
        ):
            structlog.contextvars.bind_contextvars(
                run_id=session.run_id,
                trace_id=session.trace_id,
            )
            try:
                bindings = _resolve_bindings(session, self._ctx, self._machine_resolver)
                session.bindings = bindings
                driver = _resolve_driver(session, self._ctx)
                providers = _resolve_run_providers(bindings, self._ctx)
                with plane_bindings_scope(bindings):
                    await _bind_sandbox_runtime(session, providers.sandbox, providers.file_store)
                    descriptor_registry = _resolve_descriptor_registry(self._ctx)
                    with bind_backends(self._hub), bind_descriptors(descriptor_registry):
                        await _stage_machine_attachments(
                            session,
                            providers.file_store,
                            self._machine_resolver,
                        )
                        yield PreparedRun(
                            driver=driver,
                            bindings=bindings,
                            run_context=_run_context_for_session(session),
                            workspace=workspace,
                        )
            finally:
                structlog.contextvars.clear_contextvars()


async def _bind_sandbox_runtime(session: RunSession, sandbox: Any, file_store: Any) -> None:
    """Bind a selected sandbox only when both required provider planes exist."""
    if sandbox is None or file_store is None:
        return
    try:
        await bind_sandbox_runtime(
            session.run_id,
            sandbox,
            file_store,
            session.attachment_ids,
        )
    except Exception as exc:
        structlog.get_logger(__name__).warning(
            "sandbox_runtime_bind_failed",
            hop="H2",
            run_id=session.run_id,
            error=str(exc),
        )


__all__ = ["PreparedRun", "RunExecutionEnvironment"]
