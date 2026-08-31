"""Profile-selectable evaluator for declarative phase-graph loop guards."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.protocols.gate.loop_guard import LoopGuardEvaluator
from lca.harness.declarative.execute.loop_guard import DeclarativeLoopGuardEvaluator
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    """The default evaluator has no deployment-specific settings."""

    model_config = {"extra": "forbid"}


@plugin(
    id="lca-declarative-loop-guard",
    requires=[],
    provides=["loop_guard_evaluator"],
    implements=[LoopGuardEvaluator],
    layer="L2",
    effects="none",
    kind=PluginKind.PROVIDER,
    description=(
        "Provide the default declarative LoopGuard evaluator so profiles can replace "
        "loop re-entry policy without changing the graph interpreter."
    ),
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("lca-declarative-loop-guard.checked", "lca-declarative-loop-guard.served")
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("loop_guard_evaluator",),
        emits=("loop_guard_evaluator.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Expose the default pure loop-guard evaluator to runtime assembly."""

    del config
    ctx.provide("loop_guard_evaluator", DeclarativeLoopGuardEvaluator())


__all__ = ["Config", "setup"]
