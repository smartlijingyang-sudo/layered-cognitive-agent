"""Tools Provider plugin — Tier-2 (tool factories)."""

from __future__ import annotations

from typing import cast

from pydantic import BaseModel, Field

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.protocols.runtime.infra.infra import Tool
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    factories: list[str] = Field(default_factory=lambda: ["g2a", "mcp", "tool_search"])


def _g2a_factory(bindings: object) -> list:
    # BindingsView (ADR-0220 §4.1) replaces the prior ``run`` dict. Its fields
    # are deliberately ``object | None`` (boundary DTO); narrow each to the
    # shape build_default_tools requires. A field carrying the wrong shape
    # degrades to None — build_default_tools skips the corresponding tools
    # instead of exploding inside a sub-builder. FileStore / SkillPackageStore
    # are plain Protocols (not runtime_checkable), so their shape is asserted
    # via the boundary contract: the capability registry registers each name
    # with the documented shape.
    from lca.contracts.models.cognition.boundary import BindingsView
    from lca.contracts.models.core.state.plane import PlaneBindings
    from lca.contracts.protocols.memory.operational_skills import SkillPackageStore
    from lca.contracts.protocols.runtime.infra.infra import MachineResolver, Sandbox
    from lca.infrastructure.capability.search.search import SearchService
    from lca.infrastructure.file.store import FileStore
    from lca.infrastructure.tools.default.set import build_default_tools

    b = bindings if isinstance(bindings, BindingsView) else BindingsView()
    plane_bindings = b.bindings if isinstance(b.bindings, PlaneBindings) else None
    sandbox = b.sandbox if isinstance(b.sandbox, Sandbox) else None
    search = b.search if isinstance(b.search, SearchService) else None
    machine_resolver = (
        b.machine_resolver if isinstance(b.machine_resolver, MachineResolver) else None
    )
    return build_default_tools(
        store=cast("FileStore | None", b.file_store),
        bindings=plane_bindings,
        sandbox=sandbox,
        search=search,
        skill_store=cast("SkillPackageStore | None", b.skill_store),
        machine_resolver=machine_resolver,
        fallback=False,
    )


def _mcp_factory(bindings: object) -> list:
    from lca.infrastructure.mcp.tool_set import build_ambient_mcp_tools

    return build_ambient_mcp_tools()


def _tool_search_factory(bindings: object) -> object:
    from lca.infrastructure.tool_defer.tool_search import tool_search_factory

    return tool_search_factory(bindings)


_TOOL_FACTORIES = {
    "g2a": _g2a_factory,
    "mcp": _mcp_factory,
    "tool_search": _tool_search_factory,
}


@plugin(
    id="lca-tools-provider",
    requires=["tools"],
    implements=[Tool],
    layer="L0",
    effects="tools",
    description="Register Tool factories on the ToolsService Definition (forked per-run).",
    test_suite="tests/test_plugin_tree_single_owner.py",
    kind=PluginKind.PROVIDER,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("lca-tools-provider.checked", "lca-tools-provider.served")
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    tools_seam = ctx.require("tools")
    for name in config.factories:
        factory = _TOOL_FACTORIES.get(name)
        if factory is not None:
            tools_seam.register_factory(name, factory)
