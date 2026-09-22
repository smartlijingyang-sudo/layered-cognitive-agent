"""Tests ensuring UserProfileSection and ContextSection do not duplicate memory lines."""

from __future__ import annotations

from lca.contracts.atoms.enums.enums import MemoryCategory, MemoryLayer
from lca.contracts.models.core.conversation.memory import MemoryRecord
from lca.contracts.models.core.perceive.perception import ContextItem, ContextManifest
from lca.contracts.models.team.role.team import RoleProfile
from lca.plugins.prompts.sections import ContextSection, UserProfileSection


def test_user_profile_and_context_do_not_duplicate_identity_preference():
    rec_id = MemoryRecord(
        record_id="1",
        content="用户身份：总架构师",
        memory_type=MemoryLayer.SEMANTIC,
        importance=1.0,
        category=MemoryCategory.IDENTITY,
    )
    rec_pref = MemoryRecord(
        record_id="2",
        content="偏好：只看代码",
        memory_type=MemoryLayer.SEMANTIC,
        importance=1.0,
        category=MemoryCategory.PREFERENCE,
    )
    rec_fact = MemoryRecord(
        record_id="3",
        content="数据库端口：5433",
        memory_type=MemoryLayer.SEMANTIC,
        importance=1.0,
        category=MemoryCategory.FACT,
    )

    manifest = ContextManifest(
        items=(
            ContextItem(
                kind="memory",
                payload=[rec_id, rec_pref, rec_fact],
                provenance="test",
            ),
        )
    )
    from lca.contracts.models.team.role.team import ToolPermissionManifest

    role_profile = RoleProfile(
        role="assistant",
        goal="help",
        backstory="",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=()),
    )

    profile_out = UserProfileSection().render(
        role_profile=role_profile,
        task="",
        awareness=None,
        manifest=manifest,
        tools=(),
        activated_skills=(),
    )
    context_out = ContextSection().render(
        role_profile=role_profile,
        task="",
        awareness=None,
        manifest=manifest,
        tools=(),
        activated_skills=(),
    )

    # 1. UserProfile 负责渲染身份与偏好
    assert "总架构师" in profile_out.text
    assert "只看代码" in profile_out.text

    # 2. Context 排除身份与偏好，零双写冗余
    assert "总架构师" not in context_out.text
    assert "只看代码" not in context_out.text

    # 3. Context 正常渲染客观事实
    assert "数据库端口：5433" in context_out.text
