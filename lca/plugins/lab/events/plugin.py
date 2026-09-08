# PR-A.1 — hook plugin 收编（并存期；与 agent_lab.plugins.events 双轨）
"""LCA @plugin adapter for ``agent_lab.plugins.events.EventSinkPlugin``.

This module is the parallel LCA plugin entry point for the agent_lab
event_sink hook. The hook behaviour is unchanged; the instance built
here is registered into a module-level dict so the legacy
``GraphPlugin`` registry surface (``agent_lab.plugins.base``) can
pick it up during the coexistence window. PR-A.3 will switch the
runner to consume the dict directly.

The plugin is intentionally PRIMITIVE / L4 / ``effects="none"``:
it does not perform any LCA capability wiring yet — the hook
fan-out continues to go through the lab graph's plugin registry.
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
    """Strict, empty config — behaviour is owned by the underlying hook."""

    model_config = {"extra": "forbid"}


@plugin(
    id="lab.hook.events",
    requires=[],
    provides=["lab.hooks.semantic.on_event"],
    implements=[],
    layer="L4",
    effects=EffectClass.NONE,
    kind=PluginKind.PRIMITIVE,
    description=(
        "LCA @plugin adapter for EventSinkPlugin (agent_lab event_sink hook); "
        "PR-A.1 coexistence: instance stored in _LAB_HOOKS, legacy GraphPlugin "
        "registry still owns fan-out."
    ),
    relations=(),
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G8_COLLAB,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("lab.hook.events.checked", "lab.hook.events.served"),
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("lab.hooks.*",),
        emits=("lab.hook.events.fired",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Build a GraphPlugin-compatible EventSinkPlugin instance and stash it."""
    del config
    # The legacy module imports its own registry; we only borrow the class.
    from agent_lab.plugins.events import EventSinkPlugin

    _instance = EventSinkPlugin()
    _LAB_HOOKS["lab.hook.events"] = _instance
    # Expose the same handle on the audited context for PR-A.3 consumption.
    ctx.provide("lab.hook.events", _instance)


__all__ = ["Config", "setup"]
