# PR-A.1 — hook plugin 收编（并存期；与 agent_lab.plugins.control_slots 双轨）
"""LCA @plugin adapter for ``agent_lab.plugins.control_slots.ControlSlotsPlugin``.

Owns the control-slot insertion policy on the ``before_compile`` hook:
reads the host spec's phase-tagged sub_specs and inserts sibling
control sub_specs per the wiring table. PR-A.1 stashes the instance
in a module-level dict; the legacy
``agent_lab.plugins.base.GraphPlugin`` registry still owns dispatch
until PR-A.3.
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
    id="lab.hook.control_slots",
    requires=[],
    provides=["lab.hooks.compiletime.before_compile"],
    implements=[],
    layer="L4",
    effects=EffectClass.NONE,
    kind=PluginKind.PRIMITIVE,
    description=(
        "LCA @plugin adapter for ControlSlotsPlugin (agent_lab control_slots "
        "hook); PR-A.1 coexistence: instance stored in _LAB_HOOKS, legacy "
        "GraphPlugin registry still owns dispatch."
    ),
    relations=(),
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION,
            control_slots=(ControlSlot.OBSERVE_CHECKPOINT,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "lab.hook.control_slots.checked",
                "lab.hook.control_slots.served",
            ),
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("lab.hooks.*",),
        emits=("lab.hook.control_slots.fired",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Build a GraphPlugin-compatible ControlSlotsPlugin instance."""
    del config
    from agent_lab.plugins.control_slots import ControlSlotsPlugin

    _instance = ControlSlotsPlugin()
    _LAB_HOOKS["lab.hook.control_slots"] = _instance
    ctx.provide("lab.hook.control_slots", _instance)


__all__ = ["Config", "setup"]
