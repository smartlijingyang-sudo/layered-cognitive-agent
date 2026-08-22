"""Assemble gateway runnables behind one mode-aware interface.

The HTTP run driver owns facts and execution outcome adaptation.  This module
owns the implementation details of turning a run request into an ``Agent`` or
``Team``.  Solo, cordis-creator, and team are concrete adapters because they
are real runtime variants, not hypothetical seams.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, cast

from gateway.modes import CORDIS_CREATOR_MODE_KEY, CORDIS_CREATOR_ROLE, SOLO_MODE_KEY, SOLO_ROLE
from gateway.runs.session import RunSession
from lca.contracts.atoms.ids import RunId, TraceId
from lca.contracts.mechanisms.capability import (
    MissingCapabilityError,
    provider_current,
    require_capability,
)
from lca.contracts.models.core.plane import PlaneBindings
from lca.contracts.models.observability.journal import (
    CastingCompleted,
    CastingFailed,
    CastingStarted,
    RunScope,
)
from lca.contracts.protocols import LLMAdapter
from lca.contracts.protocols.casting import CastingError, RoleLibrary, TeamCaster
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

if TYPE_CHECKING:
    from cordis import Context


class LlmResolver(Protocol):
    """Resolve the concrete LLM implementation selected by the booted profile."""

    def resolve(self) -> LLMAdapter: ...


@dataclass(frozen=True, slots=True)
class RunnableAssemblyRequest:
    """All run-scoped inputs needed to assemble a runnable."""

    session: RunSession
    question: str
    mode: str
    observability: BoundObservability
    bindings: PlaneBindings | None
    scope: Context | None
    llm_resolver: LlmResolver


@dataclass(frozen=True, slots=True)
class RunnableBuildRequest:
    """Assembly inputs after profile-backed dependencies are materialized."""

    assembly: RunnableAssemblyRequest
    llm: LLMAdapter
    tools: tuple[Tool, ...]


class RunnableAdapter(Protocol):
    """Build one concrete runnable implementation for a selected run mode."""

    async def build(self, request: RunnableBuildRequest) -> Agent | Team: ...


class SoloRunnableAdapter:
    """Build the standard single-Agent runnable."""

    async def build(self, request: RunnableBuildRequest) -> Agent:
        session = request.assembly.session
        return build_solo_agent(
            request.llm,
            observability=request.assembly.observability,
            role=session.agent.name,
            bindings=request.assembly.bindings,
            scope=request.assembly.scope,
            tools=request.tools,
        )


class CordisCreatorRunnableAdapter:
    """Build the constrained cordis-creator Agent runnable."""

    async def build(self, request: RunnableBuildRequest) -> Agent:
        return build_cordis_creator_agent(
            request.llm,
            observability=request.assembly.observability,
            scope=request.assembly.scope,
            tools=request.tools,
        )


class TeamRunnableAdapter:
    """Cast and build the Team runnable for all non-single-agent modes."""

    async def build(self, request: RunnableBuildRequest) -> Team:
        session = request.assembly.session
        return await build_runnable_team(
            request.assembly.question,
            request.llm,
            observability=request.assembly.observability,
            trace_id=session.trace_id,
            run_id=session.run_id,
            bindings=request.assembly.bindings,
            scope=request.assembly.scope,
            tools=request.tools,
        )


class CognitiveRunnableAssembler:
    """Deep module that selects a runnable adapter and materializes dependencies.

    The public interface is deliberately small: callers supply one
    :class:`RunnableAssemblyRequest` and receive a runnable.  Tool
    materialization, LLM resolution, and mode-specific object-graph knowledge
    remain inside this module.
    """

    def __init__(
        self,
        *,
        adapters: dict[str, RunnableAdapter] | None = None,
        fallback: RunnableAdapter | None = None,
    ) -> None:
        self._adapters = dict(
            adapters
            or {
                SOLO_MODE_KEY: SoloRunnableAdapter(),
                CORDIS_CREATOR_MODE_KEY: CordisCreatorRunnableAdapter(),
            }
        )
        self._fallback = fallback or TeamRunnableAdapter()

    async def assemble(self, request: RunnableAssemblyRequest) -> Agent | Team:
        """Materialize profile dependencies and delegate to the selected adapter."""

        prepared = RunnableBuildRequest(
            assembly=request,
            llm=request.llm_resolver.resolve(),
            tools=tools_from_scope(request.scope, request.bindings),
        )
        adapter = self._adapters.get(request.mode, self._fallback)
        return await adapter.build(prepared)


def tools_from_scope(scope: Context | None, bindings: PlaneBindings | None) -> tuple[Tool, ...]:
    """Materialize tools from the booted tools seam; missing seams fail loudly."""

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


def build_solo_agent(
    llm: LLMAdapter,
    *,
    observability: BoundObservability,
    role: str = SOLO_ROLE,
    bindings: PlaneBindings | None = None,
    scope: Context | None = None,
    tools: Sequence[Tool] | None = None,
) -> Agent:
    """Build a single Agent; identity comes from ``AgentRef.name``."""

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


def filter_creator_tools(tools: Sequence[Tool] | None) -> dict[str, Tool]:
    """Keep the creator tool subset and fail loudly when skill loading is absent."""

    creator_names = {"file_write", "bash", "activate_skill", "read_skill_reference"}
    filtered = {tool.name: tool for tool in tools or () if tool.name in creator_names}
    if "activate_skill" not in filtered:
        raise RuntimeError(
            "cordis-creator profile booted without `activate_skill` tool; "
            "PERSONA_GOAL instructs the model to load bundled skills via "
            "activate_skill. Check that bundles/web-app.yaml (or the active "
            "profile) registers operational skill tools. Bundled skills "
            "missing from the skill store: run `lca-ops debug tree` and "
            "inspect `ctx.skills.current().list_installed()`."
        )
    return filtered


def build_cordis_creator_agent(
    llm: LLMAdapter,
    *,
    observability: BoundObservability,
    scope: Context | None = None,
    tools: Sequence[Tool] | None = None,
) -> Agent:
    """Build the cordis-creator Agent with its explicit, reduced tool set."""

    creator_tools = filter_creator_tools(tools)

    from lca.plugins.roles.cordis_creator import build_cordis_creator_role_profile

    creator_profile = build_cordis_creator_role_profile()
    composer_factory = None
    if scope is not None:
        try:
            composer_factory = require_capability(scope, "composer.compose_factory")
        except MissingCapabilityError:
            composer_factory = None

    if composer_factory is not None:
        try:
            composer = composer_factory(scope)
            from lca.plugins.tools.cordis_control import build_cordis_control_tool

            creator_tools["cordis_control"] = build_cordis_control_tool(
                composer=composer,
                caller_grant=(
                    "cordis_control.inspect",
                    "cordis_control.author",
                    "cordis_control.validate",
                    "cordis_control.promote",
                    "tool_fs.read",
                    "tool_fs.write",
                    "tool_bash",
                    "file_write",
                ),
                actor_role=CORDIS_CREATOR_ROLE,
            )
        except Exception as exc:
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


async def build_runnable_team(
    objective: str,
    llm: LLMAdapter,
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
    """Cast the Team and close its declared governance strategy."""

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
        observability=observability,
        bindings=bindings,
        scope=scope,
        tools=tools,
    )


__all__ = [
    "CognitiveRunnableAssembler",
    "CordisCreatorRunnableAdapter",
    "LlmResolver",
    "RunnableAdapter",
    "RunnableAssemblyRequest",
    "RunnableBuildRequest",
    "SoloRunnableAdapter",
    "TeamRunnableAdapter",
    "build_cordis_creator_agent",
    "build_runnable_team",
    "build_solo_agent",
    "filter_creator_tools",
    "tools_from_scope",
]
