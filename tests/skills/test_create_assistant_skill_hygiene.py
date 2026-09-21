from lca.infrastructure.path import get_lca_home
from lca.infrastructure.tools.skills.search.tool import SkillSearchTool


def test_create_assistant_skill_has_no_leaked_profile_or_admin_hints() -> None:
    lca_home = get_lca_home()
    skill_path = lca_home / "skills" / "create-assistant" / "SKILL.md"
    assert skill_path.exists(), f"Skill file {skill_path} does not exist"
    content = skill_path.read_text(encoding="utf-8")

    # 严禁泄露内部配置文件名、profile名与运维指引
    assert "web-assistant" not in content, "Leaked 'web-assistant' internal profile"
    assert "profile" not in content.lower(), "Leaked 'profile' keyword"
    assert "系统管理员" not in content, "Leaked '系统管理员' instruction"

    # 严禁把内部状态机技术名词直接作为面向用户的教学说明
    assert "五状态状态机" not in content

    # 确保核心交互工具与五步SOP存在
    assert "askUserQuestion" in content
    assert "create_assistant" in content


def test_search_skill_tool_description_no_misleading_prompt() -> None:
    desc = SkillSearchTool.description
    assert "不会做的任务先搜这里" not in desc, (
        "search_skill prompt contains misleading trigger phrase"
    )
