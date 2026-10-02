"""Contract tests for ADR-0262 C1: the independent skill-duty prompt block.

C1 裁决：独立 skill 义务提示块（不并入 tools 段），落在 memory_retrieval
之后。每轮 system prompt 携带"先查后动手"五条义务：
search-first / 无命中自建+candidate / 否定纪律 / 检索失败≠无结果 /
易变事实复验。quality 轮 bd860ed8c 落地，本文件钉住契约。
"""

from __future__ import annotations

import pytest

from lca.contracts.models.team.role.team import RoleProfile, ToolPermissionManifest
from lca.plugins.prompts.sections.skills import SkillDutySection
from lca.plugins.prompts.template_provider import _builtin_templates

_TEMPLATES = ("react_prompt", "routing_prompt", "hierarchical_prompt")


def _role() -> RoleProfile:
    return RoleProfile(
        role="助手",
        goal="g",
        backstory="b",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
        extra={"assistant_home_path": "asst"},
    )


def _rendered() -> str:
    return SkillDutySection().render(
        role_profile=_role(),
        task="",
        awareness=None,
        manifest=None,
        tools=(),
        activated_skills=(),
    ).text


@pytest.mark.parametrize("template_id", _TEMPLATES)
def test_skill_duty_present_in_all_templates(template_id: str) -> None:
    names = [ref.name for ref in _builtin_templates()[template_id].sections]
    assert "skill_duty" in names, f"{template_id}: 独立 skill 义务块缺失（0262 C1）"


@pytest.mark.parametrize("template_id", _TEMPLATES)
def test_skill_duty_immediately_follows_memory_retrieval(template_id: str) -> None:
    names = [ref.name for ref in _builtin_templates()[template_id].sections]
    assert names.index("skill_duty") == names.index("memory_retrieval") + 1, (
        f"{template_id}: skill_duty 必须紧随 memory_retrieval（0262 C1 裁决落点）"
    )


def test_skill_duty_block_pins_search_first_duty() -> None:
    text = _rendered()
    assert "search_skill" in text
    assert "先查后动手" in text


def test_skill_duty_block_pins_negation_discipline() -> None:
    # 无检索记录就说"做不到/没接通" = 幻觉
    assert "无检索记录的否定 = 幻觉" in _rendered()


def test_skill_duty_block_pins_failure_vs_empty_distinction() -> None:
    text = _rendered()
    assert "检索失败 ≠ 检索无结果" in text
    assert "SkillCatalogSensor" in text
