# PR-A.1 — hook plugin 收编（并存期；与 agent_lab.plugins.observers 双轨）
"""LCA @plugin adapter for ``agent_lab.plugins.observers.ObserverPlugin``.

Behaviour is unchanged from the legacy hook: counts node / edge / subgraph
events per plugin instance, with a configurable ``metric_prefix``. The
instance built here is stashed in a module-level dict for PR-A.3 to
consume. During the coexistence window the legacy
``agent_lab.plugins.base.GraphPlugin`` registry still owns the dispatch.
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
    """Empty config — the hook carries its own per-instance metric_prefix."""

    model_config = {"extra": "forbid"}


@plugin(
    id="lab.hook.observers",
    requires=[],
    provides=["lab.hooks.runtime.node_start"],
    implements=[],
    layer="L4",
    effects=EffectClass.NONE,
    kind=PluginKind.PRIMITIVE,
    description=(
        "LCA @plugin adapter for ObserverPlugin (agent_lab observer hook); "
        "PR-A.1 coexistence: instance stored in _LAB_HOOKS, legacy GraphPlugin "
        "registry still owns fan-out."
    ),
    relations=(),
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G12_EVIDENCE,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "lab.hook.observers.checked",
                "lab.hook.observers.served",
            ),
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("lab.hooks.*",),
        emits=("lab.hook.observers.fired",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Build a GraphPlugin-compatible ObserverPlugin instance and stash it."""
    del config
    from agent_lab.plugins.observers import ObserverPlugin

    _instance = ObserverPlugin()
    _LAB_HOOKS["lab.hook.observers"] = _instance
    ctx.provide("lab.hook.observers", _instance)


__all__ = ["Config", "setup"]
