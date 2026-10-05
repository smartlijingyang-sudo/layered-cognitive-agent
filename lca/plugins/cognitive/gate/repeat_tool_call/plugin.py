"""RepeatToolCallGate contribution — posts onto GateService (ADR-0074 PR-2)."""

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
    id="gate.repeat-tool-call",
    requires=["gates", "loop_guard_policy"],
    implements=[DecisionGate],
    layer="L1",
    effects="none",
    description="Block runaway repeat-tool-call loops.",
    test_suite="tests/scenario/plugin/test_plugin_alignment.py",
    kind=PluginKind.PRIMITIVE,
    functional_group=FunctionalGroup.G6_DECISION,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G6_DECISION, control_slots=(ControlSlot.THINK_GUARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.TURN,)),
        authority=AuthorityContract(grants=("gates.read",)),
        observability=EvidenceContract(descriptors=("policy.gate.repeat-tool-call.denied",)),
    ),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.cognition.brain.decision_gates.repeat import RepeatToolCallGate
    from lca.plugins.cognitive.gate._loop_policy import resolve_loop_policy

    policy = resolve_loop_policy(ctx)
    ctx.require("gates").add(
        lambda: RepeatToolCallGate(policy=policy),
        id="repeat-tool-call",
        slot="loop",
        order=10,
    )
