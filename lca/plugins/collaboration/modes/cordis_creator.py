"""Profile-registerable adapter and builder for the Cordis Creator run mode."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from typing import TYPE_CHECKING, cast

from pydantic import BaseModel

from lca.application.api import Agent
from lca.contracts.capabilities import (
    CORDIS_CONTROL_TOOL_FACTORY,
    CORDIS_CREATOR_ROLE,
    RUN_MODE_REGISTRY,
)
from lca.contracts.mechanisms.capability import require_capability
from lca.contracts.models.team.role_team import RoleProfile
from lca.contracts.protocols import LLMAdapter
from lca.contracts.protocols.runtime.infra import Tool
from lca.contracts.protocols.session.run_mode import ModeAdapter
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.infrastructure.observability import BoundObservability
from lca.plugins.state.run_mode_registry_seam import RunModeRegistry
from lca.plugins.tools.cordis_control import CordisControlToolFactoryProtocol
from lca.plugins.transport.webserver.handlers.runs.lifecycle.runnable_assembly import (
    RunnableBuildRequest,
)

if TYPE_CHECKING:
    from cordis import Context


_CORDIS_CREATOR_KEY = "cordis-creator"
_CORDIS_CREATOR_ROLE = "cordis-creator"
_CREATOR_CONTROL_TOOL = "cordis_control"


class Config(BaseModel):
    """The Creator adapter delegates all policy selection to capabilities."""

    model_config = {"extra": "forbid"}


def filter_creator_tools(
    tools: Sequence[Tool] | None,
    *,
    allowed_tools: Collection[str],
) -> dict[str, Tool]:
    """Select role-declared Creator tools from the materialized generic pool."""
    requested = frozenset(allowed_tools)
    materialized_names = requested - {_CREATOR_CONTROL_TOOL}
    filtered = {tool.name: tool for tool in tools or () if tool.name in materialized_names}
    missing = sorted(materialized_names - set(filtered))
    if missing:
        raise RuntimeError(
            "cordis-creator role declares unavailable tools: "
            f"{missing!r}. Check the active profile's tools provider and "
            "RoleProfile.tool_permission_manifest; inspect the capability graph "
            "with `lca-ops debug tree`."
        )
    return filtered


def build_cordis_creator_agent(
    llm: LLMAdapter,
    *,
    observability: BoundObservability,
    scope: Context | None,
    tools: Sequence[Tool] | None = None,
) -> Agent:
    """Build the Creator Agent from role and control-tool capabilities."""
    creator_profile = cast("RoleProfile", require_capability(scope, CORDIS_CREATOR_ROLE.key))
    manifest = creator_profile.tool_permission_manifest
    creator_tools = filter_creator_tools(tools, allowed_tools=manifest.allowed_tools)
    if _CREATOR_CONTROL_TOOL in manifest.allowed_tools:
        control_tool_factory = cast(
            "CordisControlToolFactoryProtocol",
            require_capability(scope, CORDIS_CONTROL_TOOL_FACTORY.key),
        )
        creator_tools[_CREATOR_CONTROL_TOOL] = control_tool_factory.create(
            scope=scope,
            actor_role=creator_profile.role,
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


class _CordisCreatorModeAdapter(ModeAdapter):
    """Build the constrained plugin-authoring Agent runnable."""

    @property
    def key(self) -> str:
        return _CORDIS_CREATOR_KEY

    @property
    def role(self) -> str:
        return _CORDIS_CREATOR_ROLE

    def matches(self, model: str) -> bool:
        return (model or "").strip().lower() == _CORDIS_CREATOR_KEY

    async def build(self, request: object) -> object:
        """Materialize the Creator Agent from the carrier-neutral build request."""
        build_request = cast("RunnableBuildRequest", request)
        return build_cordis_creator_agent(
            build_request.llm,
            observability=build_request.assembly.observability,
            scope=build_request.assembly.scope,
            tools=build_request.tools,
        )


@plugin(
    id="lca-mode-cordis-creator-default",
    provides=[],
    requires=[
        RUN_MODE_REGISTRY.key,
        CORDIS_CREATOR_ROLE.key,
        CORDIS_CONTROL_TOOL_FACTORY.key,
    ],
    implements=["ModeAdapter"],
    layer="L4",
    effects="none",
    description="Register the default Cordis Creator run-mode adapter.",
    test_suite="tests/architecture/test_run_mode_registry.py",
    kind=PluginKind.PRIMITIVE,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Register only the Creator adapter selected by this scenario entry."""
    del config
    registry = require_capability(ctx, RUN_MODE_REGISTRY.key)
    if not isinstance(registry, RunModeRegistry):
        raise TypeError("run_mode_registry must be a RunModeRegistry")
    registry.register(_CordisCreatorModeAdapter())


__all__ = [
    "_CordisCreatorModeAdapter",
    "build_cordis_creator_agent",
    "filter_creator_tools",
]
