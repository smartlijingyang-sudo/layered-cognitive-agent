"""Tests for ADR-0255 cognitive layer memory decision gates and prompt rules."""

from __future__ import annotations

from lca.contracts.models.team.role.team import RoleProfile, ToolPermissionManifest
from lca.plugins.prompts.sections.memory import MemoryRetrievalSection


def test_memory_retrieval_section_contains_adr0255_decision_tree_and_write_rules():
    sec = MemoryRetrievalSection()
    profile = RoleProfile(
        role="assistant",
        goal="g",
        backstory="b",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
        extra={"assistant_home_path": "/tmp/test_home"},
    )
    out = sec.render(
        role_profile=profile,
        task="test",
        awareness=None,
        manifest=None,
        tools=(),
        activated_skills=(),
    )
    text = out.text
    # §4.2 强制检索决策树
    assert "记忆检索义务与决策树" in text
    assert "首个 query 贴近用户原话" in text
    assert "易变事实复验" in text
    # §4.8 自省投影防指称幻觉
    assert "自省投影防幻觉" in text
    # §4.3 落笔前写盘与冲突原地修正
    assert "落笔前写盘" in text
    assert "冲突原地修正" in text
    assert "凭证红线" in text
