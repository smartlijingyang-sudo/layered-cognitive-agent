# PR-A.1 — hook plugin 收编（并存期；与 agent_lab.plugins.observation 双轨）
"""LCA @plugin adapter for ``agent_lab.plugins.observation.ObservationRenderPlugin``.

Renders a tool receipt (status / tool / result / error) into a model-visible
``text`` field on the ``on_observation`` hook. PR-A.1 stashes the instance
in a module-level dict; the legacy ``agent_lab.plugins.base.GraphPlugin``
registry still owns dispatch until PR-A.3.
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
    id="lab.hook.observation",
    requires=[],
    provides=["lab.hooks.semantic.on_observation"],
    implements=[],
    layer="L4",
    effects=EffectClass.NONE,
    kind=PluginKind.PRIMITIVE,
    description=(
        "LCA @plugin adapter for ObservationRenderPlugin (agent_lab "
        "observation_render hook); PR-A.1 coexistence: instance stored in "
        "_LAB_HOOKS, legacy GraphPlugin registry still owns dispatch."
    ),
    relations=(),
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G4_PERCEPTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "lab.hook.observation.checked",
                "lab.hook.observation.served",
            ),
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("lab.hooks.*",),
        emits=("lab.hook.observation.fired",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Build a GraphPlugin-compatible ObservationRenderPlugin instance."""
    del config
    from agent_lab.plugins.observation import ObservationRenderPlugin

    _instance = ObservationRenderPlugin()
    _LAB_HOOKS["lab.hook.observation"] = _instance
    ctx.provide("lab.hook.observation", _instance)


__all__ = ["Config", "setup"]
