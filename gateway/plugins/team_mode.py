"""Profile-registerable default adapter and builder for the Team run mode."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, cast

from pydantic import BaseModel

from gateway.runs.runnable_assembly import RunnableBuildRequest
from lca.contracts.atoms.ids import RunId, TraceId
from lca.contracts.capabilities import RUN_MODE_REGISTRY, TEAM_CASTER, TEAM_ROLE_LIBRARY
from lca.contracts.mechanisms.capability import require_capability
from lca.contracts.models.observability.journal import (
    CastingCompleted,
    CastingFailed,
    CastingStarted,
    RunScope,
)
from lca.contracts.protocols import LLMAdapter
from lca.contracts.protocols.casting import CastingError, RoleLibrary, TeamCaster
from lca.contracts.protocols.infra import Tool
from lca.contracts.protocols.run_mode import ModeAdapter
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.layer0_infra.observability import (
    BoundObservability,
    bind_backends,
    objective_preview,
    record,
    run_scope,
)
from lca.layer4_app.api import Team
from lca.layer4_app.casting import build_from_casting_plan
from lca.plugins.seam_definitions.run_mode_registry import RunModeRegistry

if TYPE_CHECKING:
    from cordis import Context

    from lca.contracts.models.core.plane import PlaneBindings


_TEAM_KEY = "team"


class Config(BaseModel):
    """The built-in Team adapter has no profile configuration."""

    model_config = {"extra": "forbid"}


def resolve_team_casting_dependencies(scope: Context | None) -> tuple[RoleLibrary, TeamCaster]:
    """Resolve profile-selected role catalog and casting policy for Team mode."""
    library = cast("RoleLibrary", require_capability(scope, TEAM_ROLE_LIBRARY.key))
    caster = cast("TeamCaster", require_capability(scope, TEAM_CASTER.key))
    return library, caster


async def build_runnable_team(
    objective: str,
    llm: LLMAdapter,
    *,
    observability: BoundObservability,
    trace_id: str,
    run_id: str,
    library: RoleLibrary,
    caster: TeamCaster,
    bindings: PlaneBindings | None = None,
    scope: Context | None = None,
    tools: Sequence[Tool] = (),
) -> Team:
    """Build one Team from profile-selected role and casting capabilities."""
    del bindings
    record_scope = RunScope(trace_id=cast("TraceId", trace_id), run_id=cast("RunId", run_id))
    with bind_backends(observability), run_scope(record_scope):
        record(CastingStarted(objective_preview=objective_preview(objective)))
        try:
            plan = await caster.cast(objective, library, llm)
        except CastingError as exc:
            record(CastingFailed(error=str(exc)))
            raise
        selected_roles = tuple(library.get(chosen.role_id).title for chosen in plan.selected)
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
        library,
        llm,
        observability=observability,
        scope=scope,
        tools=tools,
    )


class _TeamModeAdapter(ModeAdapter):
    """Build a Team runnable for the explicit team and auto modes."""

    @property
    def key(self) -> str:
        return _TEAM_KEY

    @property
    def role(self) -> str:
        return ""

    def matches(self, model: str) -> bool:
        return (model or "").strip().lower() in {_TEAM_KEY, "auto"}

    async def build(self, request: object) -> object:
        """Materialize the Team from profile-selected casting dependencies."""
        build_request = cast("RunnableBuildRequest", request)
        session = build_request.assembly.session
        library, caster = resolve_team_casting_dependencies(build_request.assembly.scope)
        return await build_runnable_team(
            build_request.assembly.question,
            build_request.llm,
            observability=build_request.assembly.observability,
            trace_id=session.trace_id,
            run_id=session.run_id,
            library=library,
            caster=caster,
            bindings=build_request.assembly.bindings,
            scope=build_request.assembly.scope,
            tools=build_request.tools,
        )


@plugin(
    id="lca-mode-team-default",
    provides=[],
    requires=[RUN_MODE_REGISTRY.key, TEAM_ROLE_LIBRARY.key, TEAM_CASTER.key],
    implements=["ModeAdapter"],
    layer="L4",
    effects="none",
    description="Register the default Team run-mode adapter.",
    test_suite="tests/architecture/test_run_mode_registry.py",
    kind=PluginKind.PRIMITIVE,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Register only the Team adapter selected by this bundle entry."""
    del config
    registry = require_capability(ctx, RUN_MODE_REGISTRY.key)
    if not isinstance(registry, RunModeRegistry):
        raise TypeError("run_mode_registry must be a RunModeRegistry")
    registry.register(_TeamModeAdapter())


__all__ = ["_TeamModeAdapter", "build_runnable_team", "resolve_team_casting_dependencies"]
