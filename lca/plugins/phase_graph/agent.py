"""Default executable primitive for ``NodeType.AGENT`` collaboration nodes."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.capabilities import GRAPH_NODE_EXECUTORS
from lca.contracts.models.core.result import Result
from lca.contracts.models.team.graph import NodeType
from lca.contracts.protocols.collaboration.graph_node_executor import (
    GraphNodeExecutionContext,
    GraphNodeExecutor,
)
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress


class Config(BaseModel):
    """The standard agent-node primitive has no configuration."""

    model_config = {"extra": "forbid"}


class AgentGraphNodeExecutor(GraphNodeExecutor):
    """Invoke the graph-selected Team member for one Agent node."""

    node_type = NodeType.AGENT
    is_aggregator = False

    async def execute(self, context: GraphNodeExecutionContext) -> Result:
        """Resolve the declared role, invoke it, and persist the existing graph state."""

        role = context.node.config.get("role", "")
        member = next(
            (
                candidate
                for candidate in context.stage.members
                if candidate.role_profile.role == role
            ),
            None,
        )
        if member is None:
            return Result.failed(f"Graph node {context.node.id!r}: role {role!r} not found in team")
        result = await context.stage.invoker.invoke(member, _task_for_node(context))
        if context.state_store is not None:
            await context.state_store.save(context.state)
        return result


def _task_for_node(context: GraphNodeExecutionContext) -> str:
    """Construct this member's input from the objective and completed predecessors."""

    predecessors = [
        edge.source
        for edge in context.graph.incoming(context.node.id)
        if edge.source in context.predecessor_results
        and context.predecessor_results[edge.source].output
    ]
    if not predecessors:
        return context.objective
    if len(predecessors) == 1:
        return (
            f"{context.objective}\n\nContext from previous step:\n"
            f"{context.predecessor_results[predecessors[0]].output}"
        )
    parts = [str(context.predecessor_results[node_id].output) for node_id in predecessors]
    return f"{context.objective}\n\nContext from previous steps:\n" + "\n---\n".join(parts)


@plugin(
    id="graph-node.agent.default",
    Config=Config,
    provides=[],
    requires=[GRAPH_NODE_EXECUTORS.key],
    implements=[GraphNodeExecutor],
    layer="L3",
    kind=PluginKind.PRIMITIVE,
    effects=EffectClass.NONE,
    description="Register the default Team-member execution primitive for graph Agent nodes.",
    test_suite="tests/test_graph_node_executors.py",


    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G7_EXECUTION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=('plugin.serve',),
        evidence=('graph-node_agent_default.checked', 'graph-node_agent_default.served'),
        revision="v1",
    ),
    relations=(),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Contribute the Agent-node primitive to the profile-selected registry."""

    del config
    registry = ctx.require(GRAPH_NODE_EXECUTORS.key)
    registry.register(NodeType.AGENT, AgentGraphNodeExecutor())


__all__ = ["AgentGraphNodeExecutor", "Config", "setup"]
