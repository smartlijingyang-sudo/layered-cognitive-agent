"""YAML → Agent / MultiAgentTeam 装配胶水层。

仅用于测试（不进 lca 包），把 tests/fixtures/team_scenarios/*.yaml
翻译成对 lca.layer4_app.api.Agent / MultiAgentTeam 的构造参数。
真正的组装（DI）仍然只发生在 L4 组合根内部，loader 不重新发明装配机制。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from lca.contracts.protocols import LLMAdapter, Tool
from lca.layer0_infra.tools.calculator_tool import CalculatorTool
from lca.layer4_app.api import Agent, MultiAgentTeam

# ── 工具注册表：YAML 里用字符串名引用工具 ──
_TOOL_REGISTRY: dict[str, type[Tool]] = {
    "calculator": CalculatorTool,
}

# ── 默认 fixture 路径 ──
_DEFAULT_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "team_scenarios"


@dataclass
class RoleSpec:
    """YAML 里单个角色定义。"""

    key: str
    role: str
    goal: str
    backstory: str
    tools: list[str] = field(default_factory=list)


@dataclass
class TeamSpec:
    """YAML 里单个团队定义。"""

    process: str  # hierarchical / sequential / parallel / handoff
    members: list[str] = field(default_factory=list)
    supervisor: str | None = None


@dataclass
class CaseSpec:
    """YAML 里单个测试用例定义。"""

    team: str
    objective: str
    assertions: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScenarioSpec:
    """完整场景规格：角色 + 团队 + 用例。"""

    roles: dict[str, RoleSpec]
    teams: dict[str, TeamSpec]
    cases: dict[str, CaseSpec]


def load_scenario(path: str | Path) -> ScenarioSpec:
    """从 YAML 文件加载 ScenarioSpec。

    Args:
        path: YAML 文件路径。

    Returns:
        解析后的 ScenarioSpec。

    Raises:
        FileNotFoundError: 文件不存在。
        ValueError: YAML schema 校验失败。
    """
    path = Path(path)
    if not path.is_file():
        msg = f"Scenario file not found: {path}"
        raise FileNotFoundError(msg)

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        msg = f"Scenario YAML must be a mapping, got {type(raw).__name__}"
        raise ValueError(msg)

    return _parse_scenario(raw)


def _parse_scenario(raw: dict[str, Any]) -> ScenarioSpec:
    """解析原始 YAML dict 为 ScenarioSpec。"""
    # Roles
    raw_roles = raw.get("roles", [])
    if not isinstance(raw_roles, list):
        msg = f"'roles' must be a list, got {type(raw_roles).__name__}"
        raise ValueError(msg)
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

    # Teams
    raw_teams = raw.get("teams", {})
    if not isinstance(raw_teams, dict):
        msg = f"'teams' must be a mapping, got {type(raw_teams).__name__}"
        raise ValueError(msg)
    teams: dict[str, TeamSpec] = {}
    for team_key, team_raw in raw_teams.items():
        teams[team_key] = TeamSpec(
            process=team_raw["process"],
            members=team_raw.get("members", []),
            supervisor=team_raw.get("supervisor"),
        )

    # Cases
    raw_cases = raw.get("cases", {})
    if not isinstance(raw_cases, dict):
        msg = f"'cases' must be a mapping, got {type(raw_cases).__name__}"
        raise ValueError(msg)
    cases: dict[str, CaseSpec] = {}
    for case_key, case_raw in raw_cases.items():
        cases[case_key] = CaseSpec(
            team=case_raw["team"],
            objective=case_raw["objective"],
            assertions=case_raw.get("assertions", {}),
        )

    return ScenarioSpec(roles=roles, teams=teams, cases=cases)


def _instantiate_tools(tool_names: list[str]) -> list[Tool]:
    """根据工具名列表实例化工具对象。"""
    tools: list[Tool] = []
    for name in tool_names:
        tool_cls = _TOOL_REGISTRY.get(name)
        if tool_cls is None:
            msg = f"Unknown tool {name!r}. Available: {list(_TOOL_REGISTRY.keys())}"
            raise ValueError(msg)
        tools.append(tool_cls())
    return tools


def build_agent(
    role_spec: RoleSpec,
    llm: LLMAdapter,
    *,
    max_steps: int = 10,
) -> Agent:
    """从 RoleSpec 构造 Agent 实例。"""
    tools = _instantiate_tools(role_spec.tools)
    return Agent(
        role=role_spec.role,
        goal=role_spec.goal,
        backstory=role_spec.backstory,
        tools=tools,
        llm=llm,
        max_steps=max_steps,
    )


def build_team(
    spec: ScenarioSpec,
    team_key: str,
    llm: LLMAdapter,
    *,
    supervisor_max_steps: int = 20,
) -> MultiAgentTeam:
    """从 ScenarioSpec 构造 MultiAgentTeam 实例。

    Args:
        spec: 完整场景规格。
        team_key: 团队 key（对应 YAML 里 teams 下的 key）。
        llm: 所有 agent 共用的 LLM adapter。
        supervisor_max_steps: hierarchical 模式下 supervisor 的最大步数。

    Returns:
        装配好的 MultiAgentTeam。
    """
    team_spec = spec.teams[team_key]
    members = [build_agent(spec.roles[k], llm) for k in team_spec.members]

    if team_spec.process == "hierarchical":
        if team_spec.supervisor is None:
            msg = "hierarchical team requires a 'supervisor' key"
            raise ValueError(msg)
        supervisor = build_agent(
            spec.roles[team_spec.supervisor],
            llm,
            max_steps=supervisor_max_steps,
        )
        return MultiAgentTeam(
            members=members,
            process="hierarchical",
            supervisor=supervisor,
        )

    return MultiAgentTeam(members=members, process=team_spec.process)


def list_scenarios() -> list[Path]:
    """列出默认 fixtures 目录下所有 .yaml 场景文件。"""
    return sorted(_DEFAULT_FIXTURES_DIR.glob("*.yaml"))
