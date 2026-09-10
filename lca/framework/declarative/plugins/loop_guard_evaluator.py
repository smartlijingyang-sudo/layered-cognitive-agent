"""Default ``loop_guard_evaluator`` capability provider.

Wraps the framework-owned :class:`DeclarativeLoopGuardEvaluator` as a
``@plugin`` so the interpreter can inject it through Cordis instead of
constructing it via ``__init__``.  Profiles retain the ability to
override this capability with a domain-specific evaluator without
touching the interpreter module.
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
from lca.contracts.protocols.gate.loop_guard import LoopGuardEvaluator
from lca.harness.declarative.execute.loop_guard import DeclarativeLoopGuardEvaluator
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    """The default loop-guard evaluator has no deployment-specific settings."""

    model_config = {"extra": "forbid"}


@plugin(
    id="declarative.loop_guard_evaluator",
    requires=[],
    provides=["loop_guard_evaluator"],
    implements=[LoopGuardEvaluator],
    layer="L2",
    effects="none",
    kind=PluginKind.PROVIDER,
    description=(
        "Provide the default declarative LoopGuardEvaluator so profiles can "
        "replace loop re-entry policy without changing the interpreter plugin."
    ),
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "declarative.loop_guard_evaluator.checked",
                "declarative.loop_guard_evaluator.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("loop_guard_evaluator",),
        emits=("loop_guard_evaluator.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Expose the default declarative LoopGuardEvaluator to runtime assembly."""

    del config
    ctx.provide("loop_guard_evaluator", DeclarativeLoopGuardEvaluator())


__all__ = ["Config", "setup"]
