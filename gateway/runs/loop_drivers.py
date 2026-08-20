"""Loop drivers for the /runs HTTP carrier.

Each driver implements `RunLoopDriver` and is registered into a
`RunLoopDriverRegistry` provided by the `lca-run-loop-driver-registry`
plugin. Profiles swap drivers by enabling/disabling loop plugins; no
module-level singleton.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import count
from typing import TYPE_CHECKING, Any, Protocol

from gateway.modes import SOLO_MODE_KEY, SOLO_ROLE
from gateway.runs.dsh_execute import execute_dsh_session
from gateway.runs.session import RunSession
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.plane import PlaneBindings
from lca.contracts.models.observability.journal import InboxFollowupCreated
from lca.layer0_infra.observability import record
from lca.contracts.models.observability.journal import (
    CastingCompleted,
    CastingFailed,
    CastingStarted,
    RunScope,
)
from lca.contracts.models.team.run_context import RunContext
from lca.contracts.protocols.casting import (
    CastingError,
    RoleLibrary,
    TeamCaster,
)
from lca.layer0_infra.observability import (
    ObservabilityHub,
    bind,
    objective_preview,
    record,
    run_scope,
)
from lca.layer0_infra.tools.default_set import build_g2a_chat_tools
from lca.layer3_agent.role_library import FileRoleLibrary
from lca.layer4_app.api import Agent, Team
from lca.layer4_app.casting import LLMTeamCaster, build_from_casting_plan

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

    uses_sandbox: bool
    plane_target: str | None

    async def execute(
        self,
        session: RunSession,
        *,
        question: str,
        mode: str,
        hub: ObservabilityHub,
        bindings: Any,
        run_context: RunContext,
        ctx: Context,
    ) -> DriverOutcome: ...


class _UnknownExecutionTargetError(RuntimeError):
    """Raised when no plugin registered a driver for the requested target."""

    def __init__(self, target: str) -> None:
        super().__init__(
            f"no run_loop_driver registered for execution_target={target!r}; "
            f"enable the corresponding loop plugin in your bundle"
        )
        self.target = target


class RunLoopDriverRegistry:
    """Target → driver registry. Populated by loop plugins at boot."""

    def __init__(self) -> None:
        self._drivers: dict[str, RunLoopDriver] = {}

    def register(self, target: str, driver: RunLoopDriver) -> None:
        """Idempotent: later registration wins (for profile-driven overrides)."""
        self._drivers[target.strip().lower()] = driver

    def resolve(self, target: str) -> RunLoopDriver:
        try:
            return self._drivers[target.strip().lower()]
        except KeyError as exc:
            raise _UnknownExecutionTargetError(target or "") from exc

    def targets(self) -> tuple[str, ...]:
        return tuple(sorted(self._drivers))


class CognitiveRunDriver:
    """Default driver — uses plugin-tree Resolver + Agent / Team composition."""

    uses_sandbox = True
    plane_target: str | None = None

    async def execute(
        self,
        session: RunSession,
        *,
        question: str,
        mode: str,
        hub: ObservabilityHub,
        bindings: Any,
        run_context: RunContext,
        ctx: Context | None = None,
        llm_resolver: Any | None = None,
    ) -> DriverOutcome:
        _record_inbox_followup(session=session, question=question, mode=mode)
        if llm_resolver is None:
            if ctx is None:
                raise TypeError(
                    "CognitiveRunDriver.execute requires ctx or llm_resolver"
                )
            llm = ctx.inject("llm_resolver").resolve(mode=mode)
            scope: Context | None = ctx
        else:
            llm = llm_resolver.resolve(mode=mode)
            # Legacy caller (tests that pre-date the cordis migration).
            # The Agent factory will lazy-boot a default one if absent.
            scope = None
        if mode == SOLO_MODE_KEY:
            runnable: Agent | Team = _build_solo_agent(
                llm,
                observability=hub,
                role=session.agent.name,
                bindings=bindings,
                scope=scope,
            )
        else:
            runnable = await _build_team(
                question,
                llm,
                observability=hub,
                trace_id=session.trace_id,
                run_id=session.run_id,
                bindings=bindings,
                scope=scope,
            )
        if mode == SOLO_MODE_KEY:
            runnable: Agent | Team = _build_solo_agent(
                llm,
                observability=hub,
                role=session.agent.name,
                bindings=bindings,
                scope=ctx,
            )
        else:
            runnable = await _build_team(
                question,
                llm,
                observability=hub,
                trace_id=session.trace_id,
                run_id=session.run_id,
                bindings=bindings,
                scope=ctx,
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
    """DSH sub-process driver (production path)."""

    uses_sandbox = False
    plane_target = "device"

    async def execute(
        self,
        session: RunSession,
        *,
        question: str,
        mode: str,
        hub: ObservabilityHub,
        bindings: Any,
        run_context: RunContext,
        ctx: Context,
    ) -> DriverOutcome:
        del question, mode, hub, bindings, run_context, ctx
        await execute_dsh_session(session)
        return DriverOutcome(success=not session.error, error=session.error)


# ── Helpers (private; nothing else in the gateway constructs an Agent/Team) ──


def _build_solo_agent(
    llm: Any,
    *,
    observability: Any,
    role: str = SOLO_ROLE,
    bindings: PlaneBindings | None = None,
    scope: Context | None = None,
) -> Agent:
    """Solo agent — identity from AgentRef.name; prompt sections left empty."""
    return Agent(
        role=role,
        goal="",
        backstory="",
        tools=build_g2a_chat_tools(bindings=bindings),
        llm=llm,
        observability=observability,
        scope=scope,
    )


async def _build_team(
    objective: str,
    llm: Any,
    *,
    observability: ObservabilityHub,
    trace_id: str,
    run_id: str,
    bindings: PlaneBindings | None = None,
    scope: Context | None = None,
    library: RoleLibrary | None = None,
    caster: TeamCaster | None = None,
) -> Team:
    """Team LLM casting — select roles + governance, then build Team."""
    resolved_library = library if library is not None else FileRoleLibrary()
    resolved_caster = caster if caster is not None else LLMTeamCaster()
    record_scope = RunScope(trace_id=trace_id, run_id=run_id)
    with bind(observability), run_scope(record_scope):
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
        observability=observability,
        bindings=bindings,
        scope=scope,
    )


# Public aliases — kept so tests (and any third-party caller) can still
# import ``build_solo_agent`` / ``build_runnable_team`` from
# ``gateway.runs.loop_drivers`` after the assemble.py removal.
build_solo_agent = _build_solo_agent
build_runnable_team = _build_team


# ── Inbox followup (PR8.E.1 / D24) ────────────────────────────────

_FOLLOWUP_COUNTER = count(1)


def _record_inbox_followup(
    *, session: RunSession, question: str, mode: str
) -> None:
    """Publish an ``InboxFollowupCreated`` journal event for the run entry.

    The inbox-facts sensor folds these into the next perceive cycle.
    Best-effort: a failure here must not block run start.
    """
    try:
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
    except Exception:  # noqa: BLE001
        pass
