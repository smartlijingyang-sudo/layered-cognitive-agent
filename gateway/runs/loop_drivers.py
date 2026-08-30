"""Loop drivers for the /runs HTTP carrier.

Each driver implements `RunLoopDriver` and is registered into a
`RunLoopDriverRegistry` provided by the `lca-run-loop-driver-registry`
plugin. Profiles swap drivers by enabling/disabling loop plugins; no
module-level singleton.
"""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass
from itertools import count
from typing import TYPE_CHECKING, Any, Protocol, cast

from gateway.modes import SOLO_MODE_KEY, SOLO_ROLE
from gateway.runs.dsh_execute import execute_dsh_session
from gateway.runs.session import RunSession
from lca.contracts.atoms.ids import RunId, TraceId
from lca.contracts.mechanisms.capability import provider_current, require_capability
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.plane import PlaneBindings
from lca.contracts.models.observability.journal import (
    CastingCompleted,
    CastingFailed,
    CastingStarted,
    InboxFollowupCreated,
    RunScope,
)
from lca.contracts.models.team.run_context import RunContext
from lca.contracts.protocols.casting import (
    CastingError,
    RoleLibrary,
    TeamCaster,
)
from lca.contracts.protocols.infra import Tool
from lca.infrastructure.observability import (
    BoundObservability,
    bind_backends,
    objective_preview,
    record,
    run_scope,
)
from lca.layer3_agent.role_library import FileRoleLibrary
from lca.layer4_app.api import Agent, Team
from lca.layer4_app.casting import LLMTeamCaster, build_from_casting_plan
from lca.plugins.run_loop_driver_registry import (
    RunLoopDriverRegistry as RunLoopDriverRegistry,
)
from lca.plugins.run_loop_driver_registry import (
    _UnknownExecutionTargetError as _UnknownExecutionTargetError,
)

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
    """Default driver — uses plugin-tree Resolver + Agent / Team composition.

    Plane ownership is decided by ``session.plane`` / ``resolve_run_intent``,
    never by the driver itself.
    """

    def __init__(self, assembler: CognitiveRunnableAssembler | None = None) -> None:
        # Soft-locked per ADR-0103 §2. Main's loop_drivers had a __init__
        # accepting an assembler; the bulk port (46094979) brought main's
        # class body but lost the constructor. Tests + plugin tree
        # instantiate CognitiveRunDriver(CognitiveRunnableAssembler(...));
        # accepting None preserves both call sites.
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
        if llm_resolver is None and machine_resolver is None:
            if ctx is None:
                raise TypeError("CognitiveRunDriver.execute requires ctx or llm_resolver")
            llm = require_capability(ctx, "llm_resolver").resolve()
            scope: Context | None = ctx
        else:
            llm = llm_resolver.resolve()
            scope = None
        tools = _tools_from_ctx(scope, bindings)
        if mode == SOLO_MODE_KEY:
            runnable: Agent | Team = _build_solo_agent(
                llm,
                observability=hub,
                role=session.agent.name,
                scope=scope,
                tools=tools,
            )
        else:
            runnable = await _build_team(
                question,
                llm,
                observability=hub,
                trace_id=session.trace_id,
                run_id=session.run_id,
                scope=scope,
                tools=tools,
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


class DshRunDriver:
    """DSH sub-process driver (production path).

    Plane hint must arrive as ``plane: 'machine'`` from the wire; the driver
    never overrides the request.
    """

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
        machine_resolver: Any | None = None,
    ) -> DriverOutcome:
        # Soft-locked per ADR-0103 §2. Main's RunLifecycleCoordinator
        # forwards machine_resolver to the driver. Accept it and ignore
        # for the DSH-bridge branch (branch's driver uses bindings).
        del question, mode, hub, bindings, run_context, ctx, machine_resolver
        await execute_dsh_session(session)
        return DriverOutcome(success=not session.error, error=session.error)


# ── Helpers (private; nothing else in the gateway constructs an Agent/Team) ──


def _tools_from_ctx(scope: Context | None, bindings: PlaneBindings | None) -> tuple[Tool, ...]:
    """Materialize tools from the booted tools seam. Missing seam → fail."""
    if scope is None:
        return ()
    bind = {
        "file_store": provider_current(require_capability(scope, "file_store")),
        "bindings": bindings,
        "sandbox": provider_current(require_capability(scope, "sandbox")),
        "search": require_capability(scope, "search"),
        "skill_store": provider_current(require_capability(scope, "skills")),
    }
    return tuple(require_capability(scope, "tools").materialize(bind))


def _build_solo_agent(
    llm: Any,
    *,
    observability: Any,
    role: str = SOLO_ROLE,
    bindings: PlaneBindings | None = None,
    scope: Context | None = None,
    tools: Sequence[Tool] | None = None,
) -> Agent:
    """Solo agent — identity from AgentRef.name; prompt sections left empty."""
    del bindings
    return Agent(
        role=role,
        goal="",
        backstory="",
        tools=tools if tools is not None else (),
        llm=llm,
        observability=observability,
        scope=scope,
    )


async def _build_team(
    objective: str,
    llm: Any,
    *,
    observability: BoundObservability,
    trace_id: str,
    run_id: str,
    bindings: PlaneBindings | None = None,
    scope: Context | None = None,
    library: RoleLibrary | None = None,
    caster: TeamCaster | None = None,
    tools: Sequence[Tool] | None = None,
) -> Team:
    """Team LLM casting — select roles + governance, then build Team."""
    resolved_library = library if library is not None else FileRoleLibrary()
    if caster is not None:
        resolved_caster = caster
    else:
        from lca.plugins.seam_definitions.team_casting_prompt_renderer import (
            BuiltinCastingPromptRenderer,
        )
        resolved_caster = LLMTeamCaster(prompt_renderer=BuiltinCastingPromptRenderer())
    record_scope = RunScope(trace_id=cast("TraceId", trace_id), run_id=cast("RunId", run_id))
    with bind_backends(observability), run_scope(record_scope):
        record(CastingStarted(objective_preview=objective_preview(objective)))
        try:
            plan = await resolved_caster.cast(objective, resolved_library, llm)
        except CastingError as exc:
            record(CastingFailed(error=str(exc)))
            raise
        selected_roles = tuple(
            resolved_library.get(chosen.role_id).title for chosen in plan.selected
        )
        record(
            CastingCompleted(
                governance_kind=plan.governance_kind,
                lead_role=plan.lead_role_id or "",
                selected_roles=selected_roles,
                rationale=plan.rationale,
            )
        )
    return build_from_casting_plan(
        plan,
        resolved_library,
        llm,
        observability=observability,  # type: ignore[arg-type]
        scope=scope,
        tools=tools,
    )


# Public aliases — kept so tests (and any third-party caller) can still
# import ``build_solo_agent`` / ``build_runnable_team`` from
# ``gateway.runs.loop_drivers`` after the assemble.py removal.
build_solo_agent = _build_solo_agent
build_runnable_team = _build_team


# ── Inbox followup (PR8.E.1 / D24) ────────────────────────────────

_FOLLOWUP_COUNTER = count(1)


def _record_inbox_followup(*, session: RunSession, question: str, mode: str) -> None:
    """Publish an ``InboxFollowupCreated`` journal event for the run entry.

    The inbox-facts sensor folds these into the next perceive cycle.
    Best-effort: a failure here must not block run start.
    """
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
