# PR-A.1 — hook plugin 收编（并存期；与 agent_lab.plugins.memory_extract 双轨）
"""LCA @plugin adapter for ``agent_lab.plugins.memory_extract.MemoryExtractPlugin``.

On ``on_reflection`` derives memory candidates (lesson / correction / extra)
from a Reflection artifact and stashes them in ``ctx.payload``. PR-A.1
stashes the instance in a module-level dict; the legacy
``agent_lab.plugins.base.GraphPlugin`` registry still owns dispatch until
PR-A.3.
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
    id="lab.hook.memory_extract",
    requires=[],
    provides=["lab.hooks.semantic.on_reflection"],
    implements=[],
    layer="L4",
    effects=EffectClass.NONE,
    kind=PluginKind.PRIMITIVE,
    description=(
        "LCA @plugin adapter for MemoryExtractPlugin (agent_lab memory_extract "
        "hook); PR-A.1 coexistence: instance stored in _LAB_HOOKS, legacy "
        "GraphPlugin registry still owns dispatch."
    ),
    relations=(),
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G3_FACTS,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "lab.hook.memory_extract.checked",
                "lab.hook.memory_extract.served",
            ),
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("lab.hooks.*",),
        emits=("lab.hook.memory_extract.fired",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Build a GraphPlugin-compatible MemoryExtractPlugin instance."""
    del config
    from agent_lab.plugins.memory_extract import MemoryExtractPlugin

    _instance = MemoryExtractPlugin()
    _LAB_HOOKS["lab.hook.memory_extract"] = _instance
    ctx.provide("lab.hook.memory_extract", _instance)


__all__ = ["Config", "setup"]
