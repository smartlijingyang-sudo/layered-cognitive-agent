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
from typing import TYPE_CHECKING, Any, Protocol

from lca.agent.role_library import FileRoleLibrary
from lca.application.api import Agent, Team
from lca.application.casting import LLMTeamCaster
from lca.cognition.team.modes_catalog import SOLO_MODE_KEY, SOLO_ROLE
from lca.contracts.mechanisms.capability import provider_current, require_capability
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.plane import PlaneBindings
from lca.contracts.models.observability.journal import InboxFollowupCreated
from lca.contracts.models.team.run_context import RunContext
from lca.contracts.protocols.collaboration.casting import RoleLibrary, TeamCaster
from lca.contracts.protocols.runtime.infra import Tool
from lca.infrastructure.observability import BoundObservability, record
from lca.plugins.collaboration.modes.team import build_runnable_team
from lca.plugins.loop_drivers.registry import (
    RunLoopDriverRegistry as RunLoopDriverRegistry,
)
from lca.plugins.loop_drivers.registry import (
    _UnknownExecutionTargetError as _UnknownExecutionTargetError,
)
from lca.plugins.transport.webserver.handlers.runs.session.session import RunSession

if TYPE_CHECKING:
    from cordis import Context

    from lca.plugins.transport.webserver.handlers.runs.lifecycle.runnable_assembly import (
        CognitiveRunnableAssembler,
    )


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
        # ADR-0115: llm_resolver is the legacy standalone path; ctx is the
        # plugin-tree path used by RunLifecycleCoordinator. machine_resolver
        # is unrelated to LLM resolution — it must not influence which branch
        # picks the LLM. Bug 8d1e40e1 added ``and machine_resolver is None``
        # to this condition and caused ``AttributeError: NoneType.resolve``
        # when RunLifecycleCoordinator forwards machine_resolver but not
        # llm_resolver (the production call shape).
        del machine_resolver
        if llm_resolver is None:
            if ctx is None:
                raise TypeError("CognitiveRunDriver.execute requires ctx or llm_resolver")
            llm = require_capability(ctx, "llm_resolver").resolve()
            scope: Context | None = ctx
        else:
            llm = llm_resolver.resolve()
            scope = None
        tools = _tools_from_ctx(scope, bindings, session=session)
        if mode == SOLO_MODE_KEY:
            persona = _assistant_persona(scope, session)
            runnable: Agent | Team = _build_solo_agent(
                llm,
                observability=hub,
                role=persona.role or session.agent.name,
                goal=persona.goal,
                backstory=persona.backstory,
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


# ── Helpers (private; nothing else in the gateway constructs an Agent/Team) ──


def _tools_from_ctx(
    scope: Context | None,
    bindings: PlaneBindings | None,
    *,
    session: RunSession | None = None,
) -> tuple[Tool, ...]:
    """Materialize tools from the booted tools seam. Missing seam → fail."""
    if scope is None:
        return ()
    assistant_id = str(getattr(session, "assistant_id", "") or "").strip() if session else ""
    bind = {
        "file_store": provider_current(require_capability(scope, "file_store")),
        "bindings": bindings,
        "sandbox": provider_current(require_capability(scope, "sandbox")),
        "search": require_capability(scope, "search"),
        "skill_store": provider_current(require_capability(scope, "skills")),
        "assistant_id": assistant_id,
    }
    return tuple(require_capability(scope, "tools").materialize(bind))


def _build_solo_agent(
    llm: Any,
    *,
    observability: Any,
    role: str = SOLO_ROLE,
    goal: str = "",
    backstory: str = "",
    bindings: PlaneBindings | None = None,
    scope: Context | None = None,
    tools: Sequence[Tool] | None = None,
) -> Agent:
    """Solo agent — identity from AgentRef.name（助理绑定时由人设覆盖）。"""
    del bindings
    return Agent(
        role=role,
        goal=goal,
        backstory=backstory,
        tools=tools if tools is not None else (),
        llm=llm,
        observability=observability,
        scope=scope,
    )


def _assistant_persona(scope: Context | None, session: RunSession) -> Any:
    """解析 run 绑定的助理人设（ADR-0187 §3 D12 人设注入）。

    - 无 assistant_id / 无 catalog capability（web-standard）⇒ 空人设，
      路径逐字不变（I-A1）；
    - catalog.get 失败（未知 id / digest 不匹配）⇒ 空人设 + 不阻断
      （创建侧入口已做 fail-closed 校验，此处是运行期兜底）。

    返回 :class:`AssistantPersona`（role/goal/backstory 三元组）。
    """
    from lca.contracts.mechanisms.capability import (
        MissingCapabilityError,
        provider_current,
        require_capability,
    )
    from lca.plugins.assistant.persona import AssistantPersona, persona_from_home

    empty = AssistantPersona()
    assistant_id = str(getattr(session, "assistant_id", "") or "").strip()
    if not assistant_id or scope is None:
        return empty
    try:
        svc = require_capability(scope, "assistant.catalog")
    except MissingCapabilityError:
        return empty
    catalog = provider_current(svc)
    if catalog is None:
        return empty
    try:
        spec = catalog.get(assistant_id)
    except Exception:
        return empty
    try:
        return persona_from_home(spec.home_path)
    except Exception:
        return empty


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
    """Team LLM casting — select roles + governance, then build Team.

    Delegates to ``team.build_runnable_team`` so ``CastingStarted`` /
    ``CastingCompleted`` / ``CastingFailed`` are emitted from a single
    emitter (``lca.plugins.collaboration.modes.team``), keeping the catalog
    single-emitter constraint intact.
    """
    del bindings  # 已由 build_runnable_team 透传
    resolved_library = library if library is not None else FileRoleLibrary()
    if caster is not None:
        resolved_caster = caster
    else:
        from lca.plugins.collaboration.team_casting_prompt_renderer_seam import (
            BuiltinCastingPromptRenderer,
        )

        resolved_caster = LLMTeamCaster(prompt_renderer=BuiltinCastingPromptRenderer())
    return await build_runnable_team(
        objective,
        llm,
        observability=observability,
        trace_id=trace_id,
        run_id=run_id,
        library=resolved_library,
        caster=resolved_caster,
        scope=scope,
        tools=tools or (),
    )


# Public alias — kept so tests (and any third-party caller) can still
# import ``build_solo_agent`` from
# ``lca.plugins.transport.webserver.handlers.runs.execute.loop_drivers``
# after the assemble.py removal. ``build_runnable_team`` is imported above
# and used directly; callers should now import it from
# ``lca.plugins.collaboration.modes.team``.
build_solo_agent = _build_solo_agent


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
