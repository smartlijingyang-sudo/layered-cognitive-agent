"""Gateway 生产组队 —— 基于 mode_catalog 与 layer4_app 组合根。"""

from __future__ import annotations

from itertools import pairwise
from typing import Any

from gateway.mode_catalog import (
    AgentRoleTemplate,
    ModeDefinition,
    get_mode_definition,
    max_steps_for_role,
)
from lca.contracts.models.team.graph import EdgeType, ExecutionGraph, GraphEdge, GraphNode, NodeType
from lca.contracts.models.team.team_coordination import (
    Debate,
    FanOut,
    Graph,
    LeadMandate,
    PeerRelay,
    PeerSwarm,
    Pipeline,
)
from lca.contracts.protocols import LLMAdapter, ObservabilityBackend
from lca.layer4_app.api import Agent, Team, TeamLead


def _build_agent(
    template: AgentRoleTemplate,
    llm: LLMAdapter,
    *,
    observability: ObservabilityBackend,
    max_steps: int,
) -> Agent:
    return Agent(
        role=template.role,
        goal=template.goal,
        backstory=template.backstory,
        tools=[],
        llm=llm,
        max_steps=max_steps,
        observability=observability,
    )


def _build_linear_graph(role_names: list[str]) -> ExecutionGraph:
    graph = ExecutionGraph()
    graph.add_node(GraphNode(id="entry", type=NodeType.ENTRY))
    graph.add_node(GraphNode(id="exit", type=NodeType.EXIT))
    node_ids = ["entry"]
    for index, role in enumerate(role_names):
        node_id = f"n{index}"
        node_ids.append(node_id)
        graph.add_node(
            GraphNode(id=node_id, type=NodeType.AGENT, config={"role": role}),
        )
    node_ids.append("exit")
    for source, target in pairwise(node_ids):
        graph.add_edge(GraphEdge(source=source, target=target, type=EdgeType.FIXED))
    return graph


def _coordination_for(definition: ModeDefinition) -> Any:
    kind = definition.coordination
    if kind == "pipeline":
        return Pipeline()
    if kind == "fan_out":
        return FanOut()
    if kind == "peer_relay":
        return PeerRelay()
    if kind == "peer_swarm":
        return PeerSwarm(max_rounds=definition.max_rounds)
    if kind == "debate":
        return Debate(max_rounds=definition.max_rounds)
    if kind == "graph":
        role_names = [template.role for template in definition.member_roles]
        return Graph(execution_graph=_build_linear_graph(role_names))
    raise ValueError(f"mode {definition.key!r} has no coordination configuration")


def build_runnable(
    mode: str,
    llm: LLMAdapter,
    *,
    observability: ObservabilityBackend,
) -> Agent | Team:
    """按协作模式组装 Agent 或 Team（生产角色，非测试探针人设）。"""
    definition = get_mode_definition(mode)

    if mode == "solo":
        template = definition.member_roles[0]
        return _build_agent(
            template,
            llm,
            observability=observability,
            max_steps=max_steps_for_role(is_lead=False, is_solo=True),
        )

    members = [
        _build_agent(
            template,
            llm,
            observability=observability,
            max_steps=max_steps_for_role(is_lead=False, is_solo=False),
        )
        for template in definition.member_roles
    ]

    if definition.has_lead:
        if definition.lead_role is None:
            raise ValueError(f"mode {mode!r} requires lead_role")
        lead = _build_agent(
            definition.lead_role,
            llm,
            observability=observability,
            max_steps=max_steps_for_role(is_lead=True, is_solo=False),
        )
        mandate = LeadMandate(mode)
        return Team(
            members=members,
            lead=TeamLead(lead, mandate),
            observability=observability,
        )

    return Team(
        members=members,
        coordination=_coordination_for(definition),
        observability=observability,
    )
