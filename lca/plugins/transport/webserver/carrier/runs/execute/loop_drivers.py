"""Loop drivers for the /runs HTTP carrier.

Each driver implements ``RunLoopDriver`` and is registered into a
``RunLoopDriverRegistry`` provided by the ``lca-run-loop-driver-registry``
plugin. Profiles swap drivers by enabling/disabling loop plugins; no
module-level singleton.

ADR-0195 P3-03: ``CognitiveRunDriver`` delegates runnable assembly to
``CognitiveRunnableAssembler`` (application/run_mode_registry seam) and
only invokes ``Agent.run`` / ``Team.run`` — no inline phase graph or
mode branching.
"""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from itertools import count
from typing import TYPE_CHECKING, Any, Protocol

from lca.application.api.api import Agent
from lca.contracts.mechanisms.capability.capability import require_capability
from lca.contracts.models.core.state.lifecycle import TaskStatus
from lca.contracts.models.team.run.run_context import RunContext
from lca.infrastructure.observability import BoundObservability
from lca.plugins.loop.driver.plugin import (
    RunLoopDriverRegistry as RunLoopDriverRegistry,
)
from lca.plugins.loop.driver.plugin import (
    _UnknownExecutionTargetError as _UnknownExecutionTargetError,
)
from lca.plugins.transport.webserver.carrier.runs.lifecycle.runnable_assembly import (
    CognitiveRunnableAssembler,
    RunnableAssemblyRequest,
)
from lca.plugins.transport.webserver.handlers.runs.session.session.session import RunSession

if TYPE_CHECKING:
    from cordis import Context


@dataclass(frozen=True)
class DriverOutcome:
    success: bool
    result: Any | None = None
    waiting_input: bool = False
    snapshot: Any | None = None
    approval_request: dict[str, Any] | None = None
    resumable: Any | None = None
    error: str = ""


class RunLoopDriver(Protocol):
    """A loop provider available to the legacy HTTP carrier."""

    async def execute(
        self,
        session: RunSession,
        *,
        question: str,
        mode: str,
        hub: BoundObservability,
        bindings: Any,
        run_context: RunContext,
        ctx: Context,
    ) -> DriverOutcome: ...


class CognitiveRunDriver:
    """Default driver — assembles via ``run_mode_registry``, then ``.run()`` only."""

    def __init__(self, assembler: CognitiveRunnableAssembler | None = None) -> None:
        self._assembler = assembler

    async def execute(
        self,
        session: RunSession,
        *,
        question: str,
        mode: str,
        hub: BoundObservability,
        bindings: Any,
        run_context: RunContext,
        ctx: Context | None = None,
        llm_resolver: Any | None = None,
        machine_resolver: Any | None = None,
    ) -> DriverOutcome:
        _record_inbox_followup(session=session, question=question, mode=mode)
        if self._assembler is None:
            raise TypeError("CognitiveRunDriver requires CognitiveRunnableAssembler")
        if llm_resolver is None:
            if ctx is None:
                raise TypeError("CognitiveRunDriver.execute requires ctx or llm_resolver")
            resolver = require_capability(ctx, "llm_resolver")
            scope: Context | None = ctx
        else:
            resolver = llm_resolver
            scope = None
        runnable = await self._assembler.assemble(
            RunnableAssemblyRequest(
                session=session,
                question=question,
                mode=mode,
                observability=hub,
                bindings=bindings,
                scope=scope,
                llm_resolver=resolver,
                machine_resolver=machine_resolver,
            )
        )
        result = (
            await runnable.run(question, run_context)
            if isinstance(runnable, Agent)
            else await runnable.run(question)
        )
        if result.status == TaskStatus.INPUT_REQUIRED:
            return DriverOutcome(
                success=False,
                result=result,
                waiting_input=True,
                snapshot=result.extra.get("state_snapshot"),
                approval_request=result.extra.get("approval_request"),
                resumable=runnable,
            )
        return DriverOutcome(
            success=result.status == TaskStatus.COMPLETED,
            result=result,
            error=result.error or "",
        )


_FOLLOWUP_COUNTER = count(1)


def _record_inbox_followup(*, session: RunSession, question: str, mode: str) -> None:
    """Publish inbox followup via Session emit only (ADR-0195 P3-12)."""
    del mode
    inbox_id = f"inbox-{session.run_id}-{next(_FOLLOWUP_COUNTER)}"
    preview = question[:200] if isinstance(question, str) else ""
    with suppress(Exception):
        from lca.infrastructure.observability.meta_event_emit import emit_inbox_spliced
        from lca.infrastructure.session.emit.lifecycle_emit import resolve_run_session_writer

        writer = resolve_run_session_writer(session)
        emit_inbox_spliced(
            op="append",
            target="next_turn",
            message_ids=(inbox_id,),
            messages=({"role": "user", "content": preview},) if preview else (),
            actor="user",
            session=writer,
        )
