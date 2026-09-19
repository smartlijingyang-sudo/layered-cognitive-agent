"""Profile-registerable default adapter and builder for the Solo run mode."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, cast

from pydantic import BaseModel

from lca.application.api.api import Agent
from lca.contracts.capabilities import RUN_MODE_REGISTRY
from lca.contracts.mechanisms.capability.capability import require_capability
from lca.contracts.models.team.role.team import RoleProfile
from lca.contracts.protocols import LLMAdapter
from lca.contracts.protocols.memory.memory import MemorySystem
from lca.contracts.protocols.runtime.infra.infra import Tool
from lca.contracts.protocols.session.run.mode import ModeAdapter
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.infrastructure.observability import BoundObservability
from lca.plugins.state.run.mode_registry_seam import RunModeRegistry
from lca.plugins.transport.webserver.carrier.runs.lifecycle.runnable_assembly import (
    RunnableBuildRequest,
)

if TYPE_CHECKING:
    from cordis import Context

    from lca.contracts.models.core.state.plane import PlaneBindings


_SOLO_KEY = "solo"
_SOLO_ROLE = "助手"

# Creator host primitives register() onto the boot tools seam and would
# otherwise leak into solo via materialize(). They execute in the gateway
# process CWD, not the run sandbox plane. Solo keeps the computer catalog
# (listFiles / writeFile / runCommand / executeCode / …).
_CREATOR_HOST_TOOLS = frozenset(
    {
        "bash",
        "file_write",
        "cordis_control",
        "profile_apply",
        "profile_diff",
    }
)


def filter_solo_tools(tools: Sequence[Tool]) -> tuple[Tool, ...]:
    """Drop Creator host-CWD primitives; keep the sandbox computer set."""
    return tuple(tool for tool in tools if tool.name not in _CREATOR_HOST_TOOLS)


class Config(BaseModel):
    """The built-in Solo adapter has no profile configuration."""

    model_config = {"extra": "forbid"}


def build_solo_agent(
    llm: LLMAdapter,
    *,
    observability: BoundObservability,
    role: str = _SOLO_ROLE,
    role_profile: RoleProfile | None = None,
    bindings: PlaneBindings | None = None,
    scope: Context | None = None,
    tools: Sequence[Tool] | None = None,
    memory: MemorySystem | None = None,
    runtime_overrides: Mapping[str, object] | None = None,
) -> Agent:
    """Build the single-Agent runnable selected by the Solo mode adapter.

    ``role_profile`` (ADR-0242 D3) carries the assistant's Home persona; when
    present it fills role/goal/backstory. ``memory`` (ADR-0242 D5) selects a
    persistent per-assistant MemorySystem; the no-assistant path keeps the
    historical empty goal/backstory and the default per-run memory.
    ``runtime_overrides`` (ADR-0242 D9) carries ``profile.json.runtime``
    values; supported keys are ``max_steps`` and ``max_wall_clock_seconds``,
    applied only when present.
    """
    del bindings
    if role_profile is not None:
        role = role_profile.role or role
        goal = role_profile.goal
        backstory = role_profile.backstory
    else:
        goal = ""
        backstory = ""
    kwargs: dict[str, object] = {
        "role": role,
        "goal": goal,
        "backstory": backstory,
        "role_profile": role_profile,
        "tools": filter_solo_tools(tools if tools is not None else ()),
        "llm": llm,
        "observability": observability,
        "scope": scope,
    }
    runtime = dict(runtime_overrides or {})
    max_steps = runtime.get("max_steps")
    if isinstance(max_steps, int) and max_steps > 0:
        kwargs["max_steps"] = max_steps
    max_wall_clock = runtime.get("max_wall_clock_seconds")
    if isinstance(max_wall_clock, int) and max_wall_clock > 0:
        kwargs["max_wall_clock_seconds"] = max_wall_clock
    if memory is not None:
        kwargs["memory"] = memory
    return Agent(**kwargs)


class _SoloModeAdapter(ModeAdapter):
    """Build the standard single-Agent runnable."""

    @property
    def key(self) -> str:
        return _SOLO_KEY

    @property
    def role(self) -> str:
        return _SOLO_ROLE

    def matches(self, model: str) -> bool:
        candidate = (model or "").strip().lower()
        return not candidate or candidate == _SOLO_KEY

    async def build(self, request: object) -> object:
        """Materialize the Solo Agent from the carrier-neutral build request."""
        build_request = cast("RunnableBuildRequest", request)
        session = build_request.assembly.session
        memory = None
        if build_request.role_profile is not None and build_request.assistant_home_path:
            from lca.infrastructure.memory.assistant_memory import AssistantMemory

            memory = AssistantMemory(build_request.assistant_home_path)
        return build_solo_agent(
            build_request.llm,
            observability=build_request.assembly.observability,
            role=session.agent.name or _SOLO_ROLE,
            role_profile=build_request.role_profile,
            scope=build_request.assembly.scope,
            tools=build_request.tools,
            memory=memory,
            runtime_overrides=build_request.assistant_runtime,
        )


@plugin(
    id="lca-mode-solo-default",
    provides=[],
    requires=[RUN_MODE_REGISTRY.key],
    implements=["ModeAdapter"],
    layer="L4",
    effects="none",
    description="Register the default Solo run-mode adapter.",
    test_suite="tests/architecture/test_run_mode_registry.py",
    kind=PluginKind.PRIMITIVE,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Register only the Solo adapter selected by this bundle entry."""
    del config
    registry = require_capability(ctx, RUN_MODE_REGISTRY.key)
    if not isinstance(registry, RunModeRegistry):
        raise TypeError("run_mode_registry must be a RunModeRegistry")
    registry.register(_SoloModeAdapter())


__all__ = ["_SoloModeAdapter", "build_solo_agent", "filter_solo_tools"]
