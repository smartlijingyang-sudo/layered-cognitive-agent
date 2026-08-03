"""YAML → Agent / MultiAgentTeam 装配胶水层。

仅用于测试（不进 lca 包），把 tests/fixtures/team_scenarios/*.yaml
翻译成对 lca.layer4_app.api.Agent / MultiAgentTeam 的构造参数。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from lca.contracts.enums import TeamProcess
from lca.contracts.protocols import LLMAdapter, Tool
from lca.contracts.supervisor_mode import Recipe, SupervisorMode
from lca.layer0_infra.tools.calculator_tool import CalculatorTool
from lca.layer4_app.api import Agent, MultiAgentTeam

_TOOL_REGISTRY: dict[str, type[Tool]] = {
    "calculator": CalculatorTool,
}

_DEFAULT_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "team_scenarios"

# Legacy YAML keys → SupervisorMode (migration map for fixtures)
_GATE_PLANE_TO_MODE: dict[tuple[str | None, str | None], SupervisorMode] = {
    ("must_consult_all", None): SupervisorMode.BOARD,
    ("must_consult_all", "consultation"): SupervisorMode.BOARD,
    ("none", "routing"): SupervisorMode.ROUTING,
    ("none", "consultation"): SupervisorMode.CONSULTATION,
    (None, "routing"): SupervisorMode.ROUTING,
    (None, "consultation"): SupervisorMode.CONSULTATION,
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
    process: str
    members: list[str] = field(default_factory=list)
    supervisor: str | None = None
    recipe: str | None = None
    supervisor_mode: str | None = None
    # legacy (mapped then ignored at build)
    decision_gate: str | None = None
    supervisor_plane: str | None = None


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
        teams[team_key] = TeamSpec(
            process=team_raw.get("process", "hierarchical"),
            members=team_raw.get("members", []),
            supervisor=team_raw.get("supervisor"),
            recipe=team_raw.get("recipe"),
            supervisor_mode=team_raw.get("supervisor_mode"),
            decision_gate=team_raw.get("decision_gate"),
            supervisor_plane=team_raw.get("supervisor_plane"),
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
) -> Agent:
    tools = _instantiate_tools(role_spec.tools)
    return Agent(
        role=role_spec.role,
        goal=role_spec.goal,
        backstory=role_spec.backstory,
        tools=tools,
        llm=llm,
        max_steps=max_steps,
    )


def _resolve_mode(team_spec: TeamSpec) -> SupervisorMode | None:
    if team_spec.supervisor_mode is not None:
        return SupervisorMode(team_spec.supervisor_mode)
    if team_spec.recipe is not None:
        return None  # recipe expands mode
    key = (team_spec.decision_gate, team_spec.supervisor_plane)
    if key in _GATE_PLANE_TO_MODE:
        return _GATE_PLANE_TO_MODE[key]
    if team_spec.decision_gate == "must_consult_all":
        return SupervisorMode.BOARD
    if team_spec.supervisor_plane == "routing":
        return SupervisorMode.ROUTING
    return None


def build_team(
    spec: ScenarioSpec,
    team_key: str,
    llm: LLMAdapter,
    *,
    supervisor_max_steps: int = 20,
) -> MultiAgentTeam:
    team_spec = spec.teams[team_key]
    members = [build_agent(spec.roles[k], llm) for k in team_spec.members]
    mode = _resolve_mode(team_spec)

    if team_spec.recipe is not None:
        recipe = Recipe(team_spec.recipe)
        supervisor = None
        if team_spec.supervisor is not None:
            supervisor = build_agent(
                spec.roles[team_spec.supervisor],
                llm,
                max_steps=supervisor_max_steps,
            )
        return MultiAgentTeam(
            members=members,
            recipe=recipe,
            supervisor=supervisor,
            supervisor_mode=mode,
        )

    process = TeamProcess(team_spec.process)
    if process is TeamProcess.HIERARCHICAL:
        if team_spec.supervisor is None:
            raise ValueError("hierarchical team requires a 'supervisor' key")
        supervisor = build_agent(
            spec.roles[team_spec.supervisor],
            llm,
            max_steps=supervisor_max_steps,
        )
        return MultiAgentTeam(
            members=members,
            process=process,
            supervisor=supervisor,
            supervisor_mode=mode or SupervisorMode.CONSULTATION,
        )

    return MultiAgentTeam(members=members, process=process)


def list_scenarios() -> list[Path]:
    return sorted(_DEFAULT_FIXTURES_DIR.glob("*.yaml"))
