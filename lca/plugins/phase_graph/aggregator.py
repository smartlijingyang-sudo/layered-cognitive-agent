"""Default executable primitive for ``NodeType.AGGREGATOR`` collaboration nodes."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.capabilities import GRAPH_NODE_EXECUTORS
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.result import Result
from lca.contracts.models.core.state import Budget
from lca.contracts.models.team.graph import NodeType
from lca.contracts.protocols.collaboration.graph_node_executor import (
    GraphNodeExecutionContext,
    GraphNodeExecutor,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin

_AGGREGATOR_TRACE_PREFIX = "graph-agg"


class Config(BaseModel):
    """The standard aggregation primitive has no configuration."""

    model_config = {"extra": "forbid"}


class AggregatorGraphNodeExecutor(GraphNodeExecutor):
    """Fold available predecessor outputs into one graph result."""

    node_type = NodeType.AGGREGATOR
    is_aggregator = True

    async def execute(self, context: GraphNodeExecutionContext) -> Result:
        """Aggregate predecessor results without making an external call."""

        predecessors = [edge.source for edge in context.graph.incoming(context.node.id)]
        parts = [
            str(context.predecessor_results[node_id].output)
            for node_id in predecessors
            if node_id in context.predecessor_results
            and context.predecessor_results[node_id].output
        ]
        total_steps = sum(
            context.predecessor_results[node_id].total_steps
            for node_id in predecessors
            if node_id in context.predecessor_results
        )
        return Result(
            trace_id=_AGGREGATOR_TRACE_PREFIX,
            status=TaskStatus.COMPLETED,
            final_state_ref="",
            total_steps=total_steps or 1,
            budget_used=Budget(used_steps=total_steps or 1),
            output="\n".join(parts),
        )


@plugin(
    id="graph-node.aggregator.default",
    Config=Config,
    provides=[],
    requires=[GRAPH_NODE_EXECUTORS.key],
    implements=[GraphNodeExecutor],
    layer="L3",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    description="Register the default predecessor-result aggregation primitive for graph nodes.",
    test_suite="tests/test_graph_node_executors.py",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "graph-node_aggregator_default.checked",
                "graph-node_aggregator_default.served",
            )
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
    """Contribute the aggregation primitive to the profile-selected registry."""

    del config
    registry = ctx.require(GRAPH_NODE_EXECUTORS.key)
    registry.register(NodeType.AGGREGATOR, AggregatorGraphNodeExecutor())


__all__ = ["AggregatorGraphNodeExecutor", "Config", "setup"]
