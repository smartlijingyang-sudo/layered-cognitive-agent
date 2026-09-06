"""Tool guard service plugin — act-plane guard registry (ADR-0197)."""

from __future__ import annotations

from pydantic import BaseModel

from lca.cognition.body.guard.service import ToolGuardService
from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.capabilities import TOOL_GUARDS
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
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="tool.guards.service",
    provides=[TOOL_GUARDS.key],
    requires=[],
    layer="L1",
    effects="none",
    description="Registry for act-plane tool guard contributions (timeout, spill, …).",
    test_suite="tests/cognition/test_tool_guard_plugins.py",
    kind=PluginKind.PRIMITIVE,
    functional_group=FunctionalGroup.G7_EXECUTION,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.ACT_SAFE_BOUNDARY,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.AGENT, Scope.RUN)),
        authority=AuthorityContract(grants=("tool_guards.register",)),
        observability=EvidenceContract(descriptors=("tool.guards.service.provided",)),
    ),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    del config
    ctx.provide(TOOL_GUARDS.key, ToolGuardService())
