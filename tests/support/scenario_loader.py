"""YAML → Agent / Team 装配胶水层。

仅用于测试（不进 lca 包），把 tests/fixtures/team_scenarios/*.yaml
翻译成 lca Agent / Team 构造参数。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from lca.contracts.protocols import LLMAdapter, ObservabilityBackend, Tool
from lca.contracts.team_coordination import (
    Debate,
    FanOut,
    Graph,
    LeadMandate,
    PeerRelay,
    PeerSwarm,
    Pipeline,
)
from lca.layer0_infra.tools.calculator_tool import CalculatorTool
from lca.layer4_app.api import Agent, Team, TeamLead

_TOOL_REGISTRY: dict[str, type[Tool]] = {
    "calculator": CalculatorTool,
}

_DEFAULT_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "team_scenarios"

_COORDINATION_BUILDERS: dict[str, type] = {
    "pipeline": Pipeline,
    "fan_out": FanOut,
    "peer_relay": PeerRelay,
    "peer_swarm": PeerSwarm,
    "debate": Debate,
    "graph": Graph,
}


@dataclass
class RoleSpec:
    key: str
    role: str
    goal: str
    backstory: str
    tools: list[str] = field(default_factory=list)


@dataclass
class TeamSpec:
    members: list[str] = field(default_factory=list)
    lead_agent: str | None = None
    lead_mandate: str | None = None
    coordination: str | None = None
    max_rounds: int | None = None


@dataclass
class CaseSpec:
    team: str
    objective: str
    assertions: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScenarioSpec:
    roles: dict[str, RoleSpec]
    teams: dict[str, TeamSpec]
    cases: dict[str, CaseSpec]


def load_scenario(path: str | Path) -> ScenarioSpec:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Scenario file not found: {path}")

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError(f"Scenario YAML must be a mapping, got {type(raw).__name__}")

    return _parse_scenario(raw)


def _parse_scenario(raw: dict[str, Any]) -> ScenarioSpec:
    raw_roles = raw.get("roles", [])
    if not isinstance(raw_roles, list):
        raise ValueError(f"'roles' must be a list, got {type(raw_roles).__name__}")
    roles: dict[str, RoleSpec] = {}
    for entry in raw_roles:
        rs = RoleSpec(
            key=entry["key"],
            role=entry["role"],
            goal=entry.get("goal", ""),
            backstory=entry.get("backstory", ""),
            tools=entry.get("tools", []),
        )
        roles[rs.key] = rs

    raw_teams = raw.get("teams", {})
    if not isinstance(raw_teams, dict):
        raise ValueError(f"'teams' must be a mapping, got {type(raw_teams).__name__}")
    teams: dict[str, TeamSpec] = {}
    for team_key, team_raw in raw_teams.items():
        lead_raw = team_raw.get("lead")
        lead_agent = None
        lead_mandate = None
        if isinstance(lead_raw, dict):
            lead_agent = lead_raw.get("agent")
            lead_mandate = lead_raw.get("mandate")
        teams[team_key] = TeamSpec(
            members=team_raw.get("members", []),
            lead_agent=lead_agent,
            lead_mandate=lead_mandate,
            coordination=team_raw.get("coordination"),
            max_rounds=team_raw.get("max_rounds"),
        )

    raw_cases = raw.get("cases", {})
    if not isinstance(raw_cases, dict):
        raise ValueError(f"'cases' must be a mapping, got {type(raw_cases).__name__}")
    cases: dict[str, CaseSpec] = {}
    for case_key, case_raw in raw_cases.items():
        cases[case_key] = CaseSpec(
            team=case_raw["team"],
            objective=case_raw["objective"],
            assertions=case_raw.get("assertions", {}),
        )

    return ScenarioSpec(roles=roles, teams=teams, cases=cases)


def _instantiate_tools(tool_names: list[str]) -> list[Tool]:
    tools: list[Tool] = []
    for name in tool_names:
        tool_cls = _TOOL_REGISTRY.get(name)
        if tool_cls is None:
            raise ValueError(f"Unknown tool {name!r}. Available: {list(_TOOL_REGISTRY.keys())}")
        tools.append(tool_cls())
    return tools


def build_agent(
    role_spec: RoleSpec,
    llm: LLMAdapter,
    *,
    max_steps: int = 10,
    observability: str | ObservabilityBackend | None = None,
) -> Agent:
    tools = _instantiate_tools(role_spec.tools)
    extra: dict[str, str | ObservabilityBackend] = {}
    if observability is not None:
        extra["observability"] = observability
    return Agent(
        role=role_spec.role,
        goal=role_spec.goal,
        backstory=role_spec.backstory,
        tools=tools,
        llm=llm,
        max_steps=max_steps,
        **extra,
    )


def build_team(
    spec: ScenarioSpec,
    team_key: str,
    llm: LLMAdapter,
    *,
    lead_max_steps: int = 20,
    observability: str | ObservabilityBackend | None = None,
) -> Team:
    team_spec = spec.teams[team_key]
    members = [
        build_agent(spec.roles[k], llm, observability=observability) for k in team_spec.members
    ]

    has_lead = team_spec.lead_agent is not None
    has_coord = team_spec.coordination is not None
    if has_lead == has_coord:
        raise ValueError(f"team {team_key!r} requires exactly one of lead= or coordination=")

    if has_lead:
        assert team_spec.lead_agent is not None
        assert team_spec.lead_mandate is not None
        lead_agent = build_agent(
            spec.roles[team_spec.lead_agent],
            llm,
            max_steps=lead_max_steps,
            observability=observability,
        )
        mandate = LeadMandate(team_spec.lead_mandate)
        return Team(
            members=members, lead=TeamLead(lead_agent, mandate), observability=observability
        )

    assert team_spec.coordination is not None
    name = team_spec.coordination
    if name not in _COORDINATION_BUILDERS:
        raise ValueError(f"Unknown coordination {name!r}")
    if name == "graph":
        raise ValueError(
            "graph coordination requires execution_graph in code tests, not YAML alone"
        )
    if name in ("peer_swarm", "debate"):
        rounds = team_spec.max_rounds if team_spec.max_rounds is not None else 3
        coord = _COORDINATION_BUILDERS[name](max_rounds=rounds)
    else:
        coord = _COORDINATION_BUILDERS[name]()
    return Team(members=members, coordination=coord, observability=observability)


def list_scenarios() -> list[Path]:
    return sorted(_DEFAULT_FIXTURES_DIR.glob("*.yaml"))
