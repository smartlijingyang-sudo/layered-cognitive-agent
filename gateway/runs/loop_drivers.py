"""Loop drivers for the /runs HTTP carrier.

Each driver implements ``RunLoopDriver`` and is registered into a
``RunLoopDriverRegistry`` provided by the ``lca-run-loop-driver-registry``
plugin. Profiles swap drivers by enabling or disabling loop plugins; no
module-level singleton is used for driver selection.
"""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from itertools import count
from typing import TYPE_CHECKING, Any, Protocol

from gateway.modes import CORDIS_CREATOR_MODE_KEY, SOLO_MODE_KEY
from gateway.runs.runnable_assembly import (
    CognitiveRunnableAssembler,
    RunnableAssemblyRequest,
    RunnableBuildRequest,
    build_cordis_creator_agent,
    build_runnable_team,
    build_solo_agent,
    filter_creator_tools,
    tools_from_scope,
)
from gateway.runs.session import RunSession
from lca.contracts.mechanisms.capability import require_capability
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.plane import PlaneBindings
from lca.contracts.models.observability.journal import InboxFollowupCreated
from lca.contracts.models.team.run_context import RunContext
from lca.layer0_infra.observability import BoundObservability, record
from lca.layer4_app.api import Agent, Team
from lca.plugins.loop_drivers.registry import RunLoopDriverRegistry as RunLoopDriverRegistry
from lca.plugins.loop_drivers.registry import (
    _UnknownExecutionTargetError as _UnknownExecutionTargetError,
)

if TYPE_CHECKING:
    from cordis import Context


@dataclass(frozen=True)
class DriverOutcome:
    """The carrier-facing result of one run-loop driver execution."""

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
    """Run the cognitive loop through one deep runnable-assembly interface.

    This module deliberately owns only run facts, runnable execution, and
    carrier result adaptation.  Mode routing, profile dependency resolution,
    and Agent or Team implementation details live in
    :class:`CognitiveRunnableAssembler`.
    """

    def __init__(self, assembler: CognitiveRunnableAssembler | None = None) -> None:
        self._assembler = assembler or CognitiveRunnableAssembler(
            adapters={
                SOLO_MODE_KEY: _SoloCompatibilityAdapter(),
                CORDIS_CREATOR_MODE_KEY: _CreatorCompatibilityAdapter(),
            },
            fallback=_TeamCompatibilityAdapter(),
        )

    async def execute(
        self,
        session: RunSession,
        *,
        question: str,
        mode: str,
        hub: BoundObservability,
        bindings: PlaneBindings | None,
        run_context: RunContext,
        ctx: Context | None = None,
        llm_resolver: Any | None = None,
    ) -> DriverOutcome:
        _record_inbox_followup(session=session, question=question, mode=mode)
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


# Compatibility aliases: the public construction helpers remain importable while
# their implementation now belongs to the runnable-assembly module.
_tools_from_ctx = tools_from_scope
_filter_creator_tools = filter_creator_tools
_build_solo_agent = build_solo_agent
_build_cordis_creator_agent = build_cordis_creator_agent
_build_team = build_runnable_team


class _SoloCompatibilityAdapter:
    """Delegate through the stable solo helper so existing callers can patch it."""

    async def build(self, request: RunnableBuildRequest) -> Agent:
        session = request.assembly.session
        return _build_solo_agent(
            request.llm,
            observability=request.assembly.observability,
            role=session.agent.name,
            bindings=request.assembly.bindings,
            scope=request.assembly.scope,
            tools=request.tools,
        )


class _CreatorCompatibilityAdapter:
    """Delegate through the stable creator helper for compatibility."""

    async def build(self, request: RunnableBuildRequest) -> Agent:
        return _build_cordis_creator_agent(
            request.llm,
            observability=request.assembly.observability,
            scope=request.assembly.scope,
            tools=request.tools,
        )


class _TeamCompatibilityAdapter:
    """Delegate through the stable team helper for compatibility."""

    async def build(self, request: RunnableBuildRequest) -> Team:
        session = request.assembly.session
        return await _build_team(
            request.assembly.question,
            request.llm,
            observability=request.assembly.observability,
            trace_id=session.trace_id,
            run_id=session.run_id,
            bindings=request.assembly.bindings,
            scope=request.assembly.scope,
            tools=request.tools,
        )


# ── Inbox followup (PR8.E.1 / D24) ────────────────────────────────

_FOLLOWUP_COUNTER = count(1)


def _record_inbox_followup(*, session: RunSession, question: str, mode: str) -> None:
    """Publish an inbox fact for the run entry without blocking run start."""

    with suppress(Exception):
        record(
            InboxFollowupCreated(
                inbox_id=f"inbox-{session.run_id}-{next(_FOLLOWUP_COUNTER)}",
                actor="user",
                target="next_turn",
                priority="task" if mode == SOLO_MODE_KEY else "background",
                step=0,
                payload_preview=question[:200] if isinstance(question, str) else "",
            )
        )


__all__ = [
    "CognitiveRunDriver",
    "DriverOutcome",
    "RunLoopDriver",
    "RunLoopDriverRegistry",
    "_UnknownExecutionTargetError",
    "build_runnable_team",
    "build_solo_agent",
]
