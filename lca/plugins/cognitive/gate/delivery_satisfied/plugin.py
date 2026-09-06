"""DeliverySatisfiedGate contribution — posts onto GateService (ADR-0196)."""

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
from lca.contracts.protocols import DecisionGate
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="gate.delivery-satisfied",
    requires=["gates", "convergence_runtime"],
    implements=[DecisionGate],
    layer="L1",
    effects="none",
    description="Force respond when delivery evidence is satisfied but model keeps calling producer tools.",
    test_suite="tests/cognition/test_delivery_satisfied_gate.py",
    kind=PluginKind.PRIMITIVE,
    functional_group=FunctionalGroup.G6_DECISION,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G6_DECISION, control_slots=(ControlSlot.THINK_GUARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.TURN,)),
        authority=AuthorityContract(
            grants=("decision.read", "artifact.reference.read", "decision.rewrite")
        ),
        observability=EvidenceContract(
            descriptors=(
                "gate.delivery-satisfied.enforced",
                "convergence.evaluated.v1",
                "delivery.evidence.v1",
            )
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.cognition.brain.decision_gates.delivery.satisfied import DeliverySatisfiedGate
    from lca.cognition.convergence.runtime import ConvergenceRuntime

    runtime = ctx.require("convergence_runtime")
    if not isinstance(runtime, ConvergenceRuntime):
        raise TypeError(
            "convergence_runtime must be ConvergenceRuntime, "
            f"got {type(runtime).__name__}"
        )
    ctx.require("gates").add(
        lambda: DeliverySatisfiedGate(runtime),
        id="delivery-satisfied",
        slot="loop",
        order=35,
    )
