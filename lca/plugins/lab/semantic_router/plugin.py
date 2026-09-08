# PR-A.1 — hook plugin 收编（并存期；与 agent_lab.plugins.semantic_router 双轨）
"""LCA @plugin adapter for ``agent_lab.plugins.semantic_router.SemanticRouterPlugin``.

Maps artifact ``schema_ref`` to semantic hook events on
``after_node_execute``. PR-A.1 stashes the instance in a module-level
dict; the legacy ``agent_lab.plugins.base.GraphPlugin`` registry still
owns fan-out until PR-A.3.
"""

from __future__ import annotations

from pydantic import BaseModel

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
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin

# Module-level registry for the parallel hook instance; PR-A.3 consumes this.
_LAB_HOOKS: dict[str, object] = {}


class Config(BaseModel):
    """Empty config — the legacy hook owns its own per-instance config dict."""

    model_config = {"extra": "forbid"}


@plugin(
    id="lab.hook.semantic_router",
    requires=[],
    provides=["lab.hooks.runtime.after_node_execute"],
    implements=[],
    layer="L4",
    effects=EffectClass.NONE,
    kind=PluginKind.PRIMITIVE,
    description=(
        "LCA @plugin adapter for SemanticRouterPlugin (agent_lab semantic_router "
        "hook); PR-A.1 coexistence: instance stored in _LAB_HOOKS, legacy "
        "GraphPlugin registry still owns fan-out."
    ),
    relations=(),
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G5_COGNITION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "lab.hook.semantic_router.checked",
                "lab.hook.semantic_router.served",
            ),
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("lab.hooks.*",),
        emits=("lab.hook.semantic_router.fired",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Build a GraphPlugin-compatible SemanticRouterPlugin instance."""
    del config
    from agent_lab.plugins.semantic_router import SemanticRouterPlugin

    _instance = SemanticRouterPlugin()
    _LAB_HOOKS["lab.hook.semantic_router"] = _instance
    ctx.provide("lab.hook.semantic_router", _instance)


__all__ = ["Config", "setup"]
