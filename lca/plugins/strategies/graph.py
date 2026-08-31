"""Graph strategy factory — registers into team_strategies."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.capabilities import GRAPH_NODE_EXECUTORS, STRATEGIES
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.team.team_coordination import STRATEGY_KEY_GRAPH, Graph
from lca.contracts.protocols import (
    GraphNodeExecutorRegistryProtocol,
    TeamAssembly,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin

if TYPE_CHECKING:
    from lca.agent.orchestration_strategies import GraphStrategy


def build_graph_strategy(
    assembly: TeamAssembly,
    *,
    node_executors: GraphNodeExecutorRegistryProtocol,
) -> GraphStrategy:
    """Close GraphStrategy with the Profile-selected node primitive registry."""

    from lca.agent.orchestration_strategies import GraphStrategy

    governance = assembly.governance
    if not isinstance(governance, Graph):
        raise TypeError(f"strategy {STRATEGY_KEY_GRAPH!r} requires Graph governance")
    return GraphStrategy(
        assembly.stage,
        execution_graph=governance.execution_graph,
        node_executors=node_executors,
    )


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="strategy.graph",
    requires=[STRATEGIES.key, GRAPH_NODE_EXECUTORS.key],
    layer="L3",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    description="Register graph TeamStrategy factory.",
    test_suite="tests/test_graph_strategy.py",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("strategy_graph.checked", "strategy_graph.served")
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    del config
    node_executors = cast(
        "GraphNodeExecutorRegistryProtocol",
        ctx.require(GRAPH_NODE_EXECUTORS.key),
    )
    ctx.register(
        STRATEGIES.key,
        STRATEGY_KEY_GRAPH,
        lambda assembly: build_graph_strategy(assembly, node_executors=node_executors),
    )
