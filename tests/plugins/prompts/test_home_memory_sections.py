"""Home prompt section and memory context rendering tests (PR-3)."""

from __future__ import annotations

from lca.contracts.atoms.enums.enums import MemoryLayer
from lca.contracts.models.core.conversation.memory import MemoryRecord
from lca.contracts.models.core.perceive.perception import ContextItem, ContextManifest
from lca.contracts.models.team.role.team import RoleProfile, ToolPermissionManifest
from lca.plugins.prompts.sections import ContextSection, HomeSection
from lca.plugins.prompts.template_provider import _builtin_templates


def _profile(**extra: object) -> RoleProfile:
    return RoleProfile(
        role="r",
        goal="g",
        backstory="b",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=()),
        extra=extra,
    )


def _render_home(profile: RoleProfile) -> str:
    return (
        HomeSection()
        .render(
            role_profile=profile,
            task="",
            awareness=None,
            manifest=None,
            tools=(),
            activated_skills=(),
        )
        .text
    )


def test_home_section_renders_paths() -> None:
    text = _render_home(
        _profile(
            assistant_id="asst_1",
            assistant_home_path="/home/u/.lca/assistants/asst_1",
        )
    )
    assert "assistant_id: asst_1" in text
    assert "home_dir: /home/u/.lca/assistants/asst_1" in text
    assert "memory_dir" in text
    assert "skills_dir" in text
    assert "workspace_dir" in text
    # 目录路由规则：用户问「你的目录/配置/记忆」默认 home，文件操作才用沙箱。
    assert "目录路由" in text
    assert "默认用 home_dir" in text
    assert "workspace_dir（沙箱 /mnt/data）" in text


def test_home_section_unbound_empty() -> None:
    assert _render_home(_profile()) == ""


def test_home_section_in_builtin_react_template() -> None:
    tpl = _builtin_templates()["react_prompt"]
    names = [r.name for r in tpl.sections]
    assert "home" in names
    assert names[-1] == "home"


def test_memory_items_render_in_context() -> None:
    record = MemoryRecord(
        record_id="mem_1",
        content="我的昵称是老板",
        memory_type=MemoryLayer.SEMANTIC,
        importance=1.0,
    )
    manifest = ContextManifest(
        items=(ContextItem(kind="memory", payload=[record], provenance="memory.retrieve"),),
    )
    text = (
        ContextSection()
        .render(
            role_profile=_profile(),
            task="",
            awareness=None,
            manifest=manifest,
            tools=(),
            activated_skills=(),
        )
        .text
    )
    assert "我的昵称是老板" in text
