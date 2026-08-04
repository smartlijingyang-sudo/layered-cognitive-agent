"""Scenario runner: build Team/Agent with shared collector, run, return bundle."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lca.contracts.graph import EdgeType, ExecutionGraph, GraphEdge, GraphNode, NodeType
from lca.contracts.protocols import LLMAdapter
from lca.contracts.result import Result
from lca.contracts.team_coordination import (
    Debate,
    FanOut,
    Graph,
    LeadMandate,
    PeerRelay,
    PeerSwarm,
    Pipeline,
)
from lca.layer4_app.api import Agent, Team, TeamLead
from tests.harness.collector import InMemoryObservability, TraceBundle
from tests.harness.scripted_llm import ScriptedLLMAdapter, multi_delegate, respond
from tests.support.scenario_loader import build_agent, load_scenario


@dataclass
class RunOutcome:
    result: Result
    bundle: TraceBundle
    collector: InMemoryObservability


# Role profiles for probe runs — meaningful goal/backstory instead of
# "goal of Alice" placeholders (better real-LLM behavior and readable traces).
_PROBE_PROFILES: dict[str, tuple[str, str]] = {
    "Lead": ("统筹任务拆解、委派成员并汇总最终结论", "项目 Lead，负责协调团队分工与收口"),
    "Alice": ("从技术视角评估风险与可行性", "资深工程师，关注兼容性、性能与稳定性"),
    "Bob": ("从业务视角评估价值与合规风险", "业务负责人，关注用户接受度、转化与合规"),
    "Carol": ("补充执行与运营视角", "运营专家，关注落地与资源配置"),
    "Solo": ("独立完成任务并给出结论", "独立贡献者"),
}


def _probe_profile(role: str) -> tuple[str, str]:
    return _PROBE_PROFILES.get(role, (f"完成 {role} 的任务", f"{role} 角色"))


def _default_scripts_for_roles(roles: list[str], lead_role: str | None) -> dict[str, list[str]]:
    scripts: dict[str, list[str]] = {}
    members = [r for r in roles if r != lead_role]
    for r in members:
        scripts[r] = [respond(f"output from {r}")]
    if lead_role:
        # Board/consult gates may short-circuit; after settlement, respond.
        # Routing: explicit multi-delegate then respond.
        if members:
            scripts[lead_role] = [
                multi_delegate([(m, f"task for {m}") for m in members]),
                respond(f"lead summary by {lead_role}"),
            ]
        else:
            scripts[lead_role] = [respond(f"solo lead {lead_role}")]
    return scripts


def make_scripted_llm(
    role_keys_to_names: dict[str, str],
    *,
    lead_role_name: str | None = None,
    scripts_by_role_name: dict[str, list[str]] | None = None,
) -> ScriptedLLMAdapter:
    if scripts_by_role_name is not None:
        return ScriptedLLMAdapter(scripts_by_role_name, default_respond=True)
    names = list(role_keys_to_names.values())
    return ScriptedLLMAdapter(
        _default_scripts_for_roles(names, lead_role_name),
        default_respond=True,
    )


async def run_team_scripted(
    *,
    members: list[Agent],
    lead: TeamLead | None = None,
    coordination: Any = None,
    collector: InMemoryObservability | None = None,
    objective: str = "test objective",
) -> RunOutcome:
    col = collector or InMemoryObservability()
    team = Team(
        members=members,
        lead=lead,
        coordination=coordination,
        observability=col,
    )
    result = await team.run(objective)
    return RunOutcome(result=result, bundle=col.bundle(), collector=col)


async def run_agent_scripted(
    agent: Agent,
    task: str,
    collector: InMemoryObservability | None = None,
) -> RunOutcome:
    # Solo agent uses its own observability; re-compose pattern via Agent API
    # when collector injected at construction.
    col = collector
    result = await agent.run(task)
    if col is None:
        col = InMemoryObservability()
    return RunOutcome(result=result, bundle=col.bundle(), collector=col)


def build_linear_graph(role_names: list[str]) -> ExecutionGraph:
    """Simple entry → agents → exit chain for graph coordination tests."""
    from itertools import pairwise

    g = ExecutionGraph()
    g.add_node(GraphNode(id="entry", type=NodeType.ENTRY))
    g.add_node(GraphNode(id="exit", type=NodeType.EXIT))
    ids = ["entry"]
    for i, role in enumerate(role_names):
        nid = f"n{i}"
        ids.append(nid)
        g.add_node(GraphNode(id=nid, type=NodeType.AGENT, config={"role": role}))
    ids.append("exit")
    for a, b in pairwise(ids):
        g.add_edge(GraphEdge(source=a, target=b, type=EdgeType.FIXED))
    return g


async def run_mode(
    mode: str,
    llm: LLMAdapter,
    *,
    collector: InMemoryObservability | None = None,
    objective: str = "full-chain mode probe",
    max_rounds: int = 2,
) -> RunOutcome:
    """Build a minimal 2–3 agent team for *mode* and run with shared collector."""
    col = collector or InMemoryObservability()

    def _agent(role: str, steps: int = 5) -> Agent:
        goal, backstory = _probe_profile(role)
        return Agent(
            role=role,
            goal=goal,
            backstory=backstory,
            tools=[],
            llm=llm,
            max_steps=steps,
            observability=col,
        )

    a = _agent("Alice")
    b = _agent("Bob")
    c = _agent("Carol")

    if mode == "pipeline":
        team = Team(members=[a, b, c], coordination=Pipeline(), observability=col)
    elif mode == "fan_out":
        team = Team(members=[a, b, c], coordination=FanOut(), observability=col)
    elif mode == "peer_relay":
        team = Team(members=[a, b], coordination=PeerRelay(), observability=col)
    elif mode == "peer_swarm":
        team = Team(
            members=[a, b],
            coordination=PeerSwarm(max_rounds=max_rounds),
            observability=col,
        )
    elif mode == "debate":
        team = Team(
            members=[a, b],
            coordination=Debate(max_rounds=max_rounds),
            observability=col,
        )
    elif mode == "graph":
        g = build_linear_graph(["Alice", "Bob"])
        team = Team(
            members=[a, b],
            coordination=Graph(execution_graph=g),
            observability=col,
        )
    elif mode in ("routing", "consult", "board"):
        lead_agent = _agent("Lead", steps=15)
        mandate = LeadMandate(mode)
        team = Team(
            members=[a, b],
            lead=TeamLead(lead_agent, mandate),
            observability=col,
        )
    elif mode == "solo":
        agent = _agent("Solo")
        result = await agent.run(objective)
        return RunOutcome(result=result, bundle=col.bundle(), collector=col)
    else:
        raise ValueError(f"Unknown mode {mode!r}")

    result = await team.run(objective)
    return RunOutcome(result=result, bundle=col.bundle(), collector=col)


def load_and_build_from_yaml(
    path: str,
    team_key: str,
    llm: LLMAdapter,
    *,
    observability: Any = None,
) -> Team:
    """Load scenario YAML and build team with optional shared observability."""
    spec = load_scenario(path)
    # scenario_loader build_team doesn't pass observability — assemble manually
    team_spec = spec.teams[team_key]
    members = [
        build_agent(spec.roles[k], llm, max_steps=8)
        if observability is None
        else Agent(
            role=spec.roles[k].role,
            goal=spec.roles[k].goal,
            backstory=spec.roles[k].backstory,
            tools=[],
            llm=llm,
            max_steps=8,
            observability=observability,
        )
        for k in team_spec.members
    ]
    # Prefer scenario_loader for coordination/lead wiring when no obs
    from tests.support.scenario_loader import build_team

    if observability is None:
        return build_team(spec, team_key, llm)

    # Rebuild with observability injection
    if team_spec.lead_agent:
        lead_role = spec.roles[team_spec.lead_agent]
        lead_a = Agent(
            role=lead_role.role,
            goal=lead_role.goal,
            backstory=lead_role.backstory,
            tools=[],
            llm=llm,
            max_steps=20,
            observability=observability,
        )
        mandate = LeadMandate(team_spec.lead_mandate or "board")
        return Team(
            members=members,
            lead=TeamLead(lead_a, mandate),
            observability=observability,
        )
    name = team_spec.coordination or "pipeline"
    coord_map: dict[str, Any] = {
        "pipeline": Pipeline(),
        "fan_out": FanOut(),
        "peer_relay": PeerRelay(),
        "peer_swarm": PeerSwarm(max_rounds=team_spec.max_rounds or 2),
        "debate": Debate(max_rounds=team_spec.max_rounds or 2),
    }
    if name not in coord_map:
        raise ValueError(f"YAML runner does not support coordination={name!r} here")
    return Team(members=members, coordination=coord_map[name], observability=observability)
