"""control.observe.wildcard — explicit no-op NodeExecutor for the wildcard slot."""

from __future__ import annotations

from dataclasses import dataclass

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
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.contracts.protocols.declarative.declarative_1.ports import PortName
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.protocols.graph.routing import RoutingDecision
from lca.contracts.atoms.enums.enums import ActionType
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


@dataclass(frozen=True, slots=True)
class ObserveWildcardExecutor:
    """No-op control node: always emits ``allow`` verdict."""

    semantic_name: str = "control.observe.wildcard"
    region: str = "phase:stop"
    declared_inputs: tuple[PortName, ...] = ()
    declared_outputs: tuple[PortName, ...] = ("verdict",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        del context, input
        return NodeOutput(
            port_values={
                "verdict": {"verdict": "allow"},
                "routing": RoutingDecision(action_type=ActionType.RESPOND),
            },
        )


@plugin(
    id="control.observe.wildcard",
    provides=("phase:stop::control.observe.wildcard",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    test_suite="tests/declarative/test_control_contributions.py",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G6_DECISION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.TURN,)),
        authority=AuthorityContract(grants=("checkpoint.*",)),
        observability=EvidenceContract(
            descriptors=("control_observe_wildcard.checked", "control_observe_wildcard.served")
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: object) -> None:
    del config
    ctx.provide("phase:stop::control.observe.wildcard", ObserveWildcardExecutor())


__all__ = ["ObserveWildcardExecutor", "setup"]
