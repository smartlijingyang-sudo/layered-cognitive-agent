"""Default convergence policy provider (ADR-0196)."""

from __future__ import annotations

from pydantic import BaseModel

from lca.cognition.convergence.policy import DefaultConvergencePolicy
from lca.cognition.convergence.runtime import ConvergenceRuntime
from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.capabilities import CONVERGENCE_POLICY
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
from lca.contracts.protocols.think.convergence import ConvergencePolicy
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="convergence.policy.default",
    provides=[CONVERGENCE_POLICY.key, "convergence_runtime"],
    requires=[],
    implements=[ConvergencePolicy],
    layer="L1",
    effects="none",
    description="Provide the default convergence policy and runtime facade for gates/stop.",
    test_suite="tests/cognition/test_convergence_policy_plugin.py",
    kind=PluginKind.PRIMITIVE,
    functional_group=FunctionalGroup.G6_DECISION,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G6_DECISION,
            control_slots=(ControlSlot.THINK_GUARD, ControlSlot.STOP_DECIDE),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.AGENT, Scope.RUN)),
        authority=AuthorityContract(grants=("convergence.read", "convergence.evaluate")),
        observability=EvidenceContract(
            descriptors=(
                "convergence.policy.default.provided",
                "delivery.evidence.v1",
                "convergence.evaluated.v1",
            ),
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    del config
    policy = DefaultConvergencePolicy()
    ctx.provide(CONVERGENCE_POLICY.key, policy)
    ctx.provide("convergence_runtime", ConvergenceRuntime(policy=policy))
