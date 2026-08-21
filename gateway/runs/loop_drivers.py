"""Loop drivers for the /runs HTTP carrier.

Each driver implements `RunLoopDriver` and is registered into a
`RunLoopDriverRegistry` provided by the `lca-run-loop-driver-registry`
plugin. Profiles swap drivers by enabling/disabling loop plugins; no
module-level singleton.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass
from itertools import count
from typing import TYPE_CHECKING, Any, Protocol, cast

from gateway.modes import (
    CORDIS_CREATOR_MODE_KEY,
    CORDIS_CREATOR_ROLE,
    SOLO_MODE_KEY,
    SOLO_ROLE,
)
from gateway.runs.dsh_execute import execute_dsh_session
from gateway.runs.session import RunSession
from lca.contracts.atoms.ids import RunId, TraceId
from lca.contracts.mechanisms.capability import (
    MissingCapabilityError,
    provider_current,
    require_capability,
)
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
from lca.layer0_infra.observability import (
    BoundObservability,
    bind_backends,
    objective_preview,
    record,
    run_scope,
)
from lca.layer3_agent.role_library import FileRoleLibrary
from lca.layer4_app.api import Agent, Team
from lca.layer4_app.casting import LLMTeamCaster, build_from_casting_plan
from lca.plugins.loop_drivers.registry import (
    RunLoopDriverRegistry as RunLoopDriverRegistry,
)
from lca.plugins.loop_drivers.registry import (
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
    ) -> DriverOutcome:
        _record_inbox_followup(session=session, question=question, mode=mode)
        if llm_resolver is None:
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
                bindings=bindings,
                scope=scope,
                tools=tools,
            )
        elif mode == CORDIS_CREATOR_MODE_KEY:
            # Creator §13.3 single-port 入口：保持 web-standard booted ctx，
            # 但 persona 切到 cordis-creator + tool_permission_manifest 缩到
            # 三件创作工具（cordis_control / file_write / bash）。
            runnable = _build_cordis_creator_agent(
                llm,
                observability=hub,
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
                bindings=bindings,
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
    ) -> DriverOutcome:
        del question, mode, hub, bindings, run_context, ctx
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


def _build_cordis_creator_agent(
    llm: Any,
    *,
    observability: Any,
    scope: Context | None = None,
    tools: Sequence[Tool] | None = None,
) -> Agent:
    """Creator §13.3 single-port agent：cordis-creator persona + 创作工具集。

    设计：web-standard profile booted 后，scenario-cordis-creator bundle 把
    cordis_control / file_write / bash 三个工具都注册到 ``tools`` 服务；
    本函数从此全局工具池里**只挑这三件**，再叠加 cordis-creator 的
    persona（goal / backstory / persona_boundaries），用 list 形式传
    ``Agent.tools=``，最终 :class:`ToolPermissionManifest.allowed_tools`
    自动收敛到 cordis_control / file_write / bash 三件。
    """
    # 只从 tools 池里挑 creator 必需的 file_write / bash；cordis_control
    # 单独用 composer 工厂现场构造（需要 cordis.Context）
    creator_tools: dict[str, Tool] = {}
    for tool in tools or ():
        if tool.name in {"file_write", "bash"}:
            creator_tools[tool.name] = tool

    # 加载 cordis-creator role profile（persona + boundaries）
    from lca.plugins.roles.cordis_creator import build_cordis_creator_role_profile

    creator_profile = build_cordis_creator_role_profile()
    # 从 ctx.providers 取 Composer 工厂（cordis-creator 工具集需要；AdHoc 注入）
    composer_factory = None
    if scope is not None:
        try:
            composer_factory = require_capability(scope, "composer.compose_factory")
        except MissingCapabilityError:
            composer_factory = None

    # 现场构造 cordis_control 工具 —— 同一 session 共用一个 Composer 实例
    # （python 引用：每个工具 = 共享同一 ctx 引用），caller_grant ＝ 全集
    if composer_factory is not None:
        try:
            composer = composer_factory(scope)
            from lca.plugins.tools.cordis_control import build_cordis_control_tool

            creator_tools["cordis_control"] = build_cordis_control_tool(
                composer=composer,
                caller_grant=(
                    "cordis_control.inspect",
                    "cordis_control.mount",
                    "cordis_control.unmount",
                    "cordis_control.publish",
                    "tool_fs.read",
                    "tool_fs.write",
                    "tool_bash",
                    "file_write",
                ),
                actor_role=CORDIS_CREATOR_ROLE,
            )
        except Exception as exc:
            # Composer 工厂失败时不强求 cordis_control；file_write + bash
            # 仍足够让 agent 知道 capabilities 缺失
            logging.getLogger(__name__).warning(
                "cordis_creator.composer_resolve_failed",
                extra={"actor_role": CORDIS_CREATOR_ROLE, "error": str(exc)},
            )

    return Agent(
        role=creator_profile.role,
        goal=creator_profile.goal,
        backstory=creator_profile.backstory,
        tools=tuple(creator_tools.values()),
        llm=llm,
        observability=observability,
        scope=scope,
    )


def _reinject_cordis_control(
    original_tool: Tool,
    *,
    composer_factory: Any,
    scope: Context,
    actor_role: str,
) -> Tool:
    """用 ctx 里的 composer 工厂重绑 cordis_control（保留 preset_root 与 actor_role）。

    web-standard profile booted 后，code 上 ``ctx.inject("composer.compose_factory")``
    返回 :func:`build_composer_factory` 工厂；调用它拿到当前 session 的
    :class:`CordisComposer` 实例，重新构造一个 cordis_control（带 caller_grant 全集）。
    """
    try:
        composer = composer_factory(scope)
    except Exception:
        return original_tool

    from lca.plugins.tools.cordis_control import build_cordis_control_tool

    # 取原 tool 的 preset_root（如果构造时传过）
    preset_root = getattr(original_tool, "_preset_root", None)
    return build_cordis_control_tool(
        composer=composer,
        caller_grant=(
            "cordis_control.inspect",
            "cordis_control.mount",
            "cordis_control.unmount",
            "cordis_control.publish",
            "tool_fs.read",
            "tool_fs.write",
            "tool_bash",
            "file_write",
        ),
        actor_role=actor_role,
        preset_root=preset_root,
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
    resolved_caster = caster if caster is not None else LLMTeamCaster()
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
        bindings=bindings,
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
