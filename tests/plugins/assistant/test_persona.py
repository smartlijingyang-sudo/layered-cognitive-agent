"""persona_from_home tests（助理人设 → RoleProfile 三元组）。

覆盖：完整 Home ⇒ role/goal/backstory 收敛；文件缺失 ⇒ 空字段降级；
backstory 截断上限；``build_solo_agent`` 的 role_profile 注入（ADR-0242 D3）。
"""

from __future__ import annotations

from pathlib import Path

from lca.contracts.models.team.role.team import RoleProfile, ToolPermissionManifest
from lca.plugins.assistant.home._home_layout import render_template, write_home_files
from lca.plugins.assistant.persona.persona import persona_from_home
from lca.plugins.collaboration.modes.solo import build_solo_agent
from tests.harness.collector import InMemoryObservability
from tests.harness.scripted_llm import ScriptedLLMAdapter


def _materialize(home: Path, template_id: str = "assistant.research") -> None:
    rendered = render_template(template_id, name="小研", description="深度研究")
    write_home_files(home, rendered.files)


class TestPersonaFromHome:
    def test_full_home_resolves_persona(self, tmp_path: Path) -> None:
        home = tmp_path / "asst_x"
        _materialize(home)
        persona = persona_from_home(str(home))
        assert persona.role == "小研"
        assert persona.goal == "深度研究"
        assert "研究助理" in persona.backstory
        assert "USER" in persona.backstory

    def test_missing_home_degrades_to_empty(self, tmp_path: Path) -> None:
        persona = persona_from_home(str(tmp_path / "nope"))
        assert persona.role == ""
        assert persona.goal == ""
        assert persona.backstory == ""

    def test_backstory_truncated(self, tmp_path: Path) -> None:
        home = tmp_path / "asst_big"
        _materialize(home)
        (home / "SOUL.md").write_text("字" * 8000, encoding="utf-8")
        persona = persona_from_home(str(home))
        assert len(persona.backstory) <= 3000

    def test_goal_falls_back_to_first_goal_name(self, tmp_path: Path) -> None:
        home = tmp_path / "asst_nongoal"
        _materialize(home)
        (home / "profile.json").write_text(
            '{"name": "小研", "description": "", "emoji": "🔍", "status": "active"}',
            encoding="utf-8",
        )
        persona = persona_from_home(str(home))
        assert persona.goal == "深度研究"  # goals.yaml 第一个 goal 的 name


class TestBuildSoloAgentRoleProfile:
    """``build_solo_agent`` 的 role_profile 注入（ADR-0242 D3 / I-B1）。"""

    def test_role_profile_fills_role_goal_backstory(self) -> None:
        llm = ScriptedLLMAdapter({}, default_respond=True)
        profile = RoleProfile(
            role="数据分析师",
            goal="提供数据洞察",
            backstory="你是数据分析师，擅长 SQL 与可视化。",
            tool_permission_manifest=ToolPermissionManifest(allowed_tools=()),
        )
        agent = build_solo_agent(
            llm,
            observability=InMemoryObservability(),
            role_profile=profile,
        )
        assert agent.role_profile.role == "数据分析师"
        assert agent.role_profile.goal == "提供数据洞察"
        assert agent.role_profile.backstory == "你是数据分析师，擅长 SQL 与可视化。"

    def test_without_role_profile_keeps_empty_goal_and_backstory(self) -> None:
        llm = ScriptedLLMAdapter({}, default_respond=True)
        agent = build_solo_agent(llm, observability=InMemoryObservability())
        assert agent.role_profile.goal == ""
        assert agent.role_profile.backstory == ""

    def test_empty_role_profile_role_falls_back_to_default(self) -> None:
        llm = ScriptedLLMAdapter({}, default_respond=True)
        profile = RoleProfile(
            role="",
            goal="目标",
            backstory="背景",
            tool_permission_manifest=ToolPermissionManifest(allowed_tools=()),
        )
        agent = build_solo_agent(
            llm,
            observability=InMemoryObservability(),
            role="自定义角色",
            role_profile=profile,
        )
        assert agent.role_profile.role == "自定义角色"
        assert agent.role_profile.goal == "目标"
        assert agent.role_profile.backstory == "背景"

    def test_runtime_overrides_flow_into_agent_spec(self) -> None:
        """ADR-0242 D9:profile.json.runtime 的 max_steps / max_wall_clock 生效。"""
        llm = ScriptedLLMAdapter({}, default_respond=True)
        agent = build_solo_agent(
            llm,
            observability=InMemoryObservability(),
            runtime_overrides={"max_steps": 9, "max_wall_clock_seconds": 123},
        )
        assert agent.spec.max_steps == 9
        assert agent.spec.max_wall_clock_seconds == 123

    def test_runtime_overrides_ignored_when_absent(self) -> None:
        """无 runtime 覆盖时保留默认值，不传 None 破坏 Agent 构造。"""
        llm = ScriptedLLMAdapter({}, default_respond=True)
        agent = build_solo_agent(
            llm,
            observability=InMemoryObservability(),
            runtime_overrides={},
        )
        assert agent.spec.max_steps > 0
        assert agent.spec.max_wall_clock_seconds is None or agent.spec.max_wall_clock_seconds > 0

    def test_runtime_overrides_reject_non_positive(self) -> None:
        """非正数 / 非 int 的 runtime 值被忽略（fail-soft，不覆盖默认）。"""
        llm = ScriptedLLMAdapter({}, default_respond=True)
        agent = build_solo_agent(
            llm,
            observability=InMemoryObservability(),
            runtime_overrides={"max_steps": 0, "max_wall_clock_seconds": "abc"},
        )
        assert agent.spec.max_steps > 0
