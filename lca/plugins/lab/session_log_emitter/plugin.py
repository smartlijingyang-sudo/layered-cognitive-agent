# PR-A.1 — hook plugin 收编（并存期；与 agent_lab.nodes.session_log.plugin 双轨）
"""LCA @plugin adapter for ``agent_lab.nodes.session_log.plugin.SessionLogEmitterPlugin``.

Bridges framework lifecycle hooks (node_start / node_end / edge_fire /
subgraph_enter / subgraph_exit / before_compile / after_compile) into
the Session via the ``session_log._sink``. PR-A.1 stashes the instance
in a module-level dict; the legacy
``agent_lab.plugins.base.GraphPlugin`` registry still owns dispatch until
PR-A.3.

The plugin's ``name="default_session_log_emitter"`` is the existing
``kind="session_log_emitter"`` lookup key used by spec-level ``plugins:``
entries; do not change it without updating the same-string references in
graph yaml.
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
    id="lab.hook.session_log_emitter",
    requires=[],
    provides=["lab.hooks.semantic.on_event"],
    implements=[],
    layer="L4",
    effects=EffectClass.NONE,
    kind=PluginKind.PRIMITIVE,
    description=(
        "LCA @plugin adapter for SessionLogEmitterPlugin (agent_lab "
        "session_log_emitter hook); PR-A.1 coexistence: instance stored in "
        "_LAB_HOOKS, legacy GraphPlugin registry still owns dispatch."
    ),
    relations=(),
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G12_EVIDENCE,
            control_slots=(ControlSlot.OBSERVE_CHECKPOINT,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "lab.hook.session_log_emitter.checked",
                "lab.hook.session_log_emitter.served",
            ),
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("lab.hooks.*",),
        emits=("lab.hook.session_log_emitter.fired",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Build a GraphPlugin-compatible SessionLogEmitterPlugin instance."""
    del config
    from agent_lab.nodes.session_log.plugin import SessionLogEmitterPlugin

    _instance = SessionLogEmitterPlugin()
    _LAB_HOOKS["lab.hook.session_log_emitter"] = _instance
    ctx.provide("lab.hook.session_log_emitter", _instance)


__all__ = ["Config", "setup"]
