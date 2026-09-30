"""Side-chat isolation: branch writes, cross-chat retrieval, privacy firewall."""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.contracts.models.team.role.team import RoleProfile, ToolPermissionManifest
from lca.infrastructure.memory.assistant_memory import AssistantMemory
from lca.infrastructure.tools.assistant.memory_tools import MemoryAddTool, MemorySearchTool
from lca.plugins.prompts.sections.memory import PrivacyFirewallSection


@pytest.mark.asyncio
async def test_branch_write_lands_in_side_chat_and_main_stays_unchanged(tmp_path: Path) -> None:
    memory = AssistantMemory(tmp_path / "asst")
    add = MemoryAddTool(memory=memory)
    await add.execute({"content": "用户住在杭州", "category": "fact"})
    obs = await add.execute({"content": "国庆行程去北京", "category": "fact", "branch": "chat-123"})
    assert obs.success is True
    assert obs.payload["branch"] == "chat-123"
    branch = tmp_path / "asst" / "side-chats" / "chat-123" / "MEMORY.md"
    assert branch.is_file()
    assert "国庆行程去北京" in branch.read_text(encoding="utf-8")
    main_md = (tmp_path / "asst" / "MEMORY.md").read_text(encoding="utf-8")
    assert "国庆行程去北京" not in main_md
    assert "用户住在杭州" in main_md


@pytest.mark.asyncio
async def test_retrieval_reads_main_and_branch(tmp_path: Path) -> None:
    memory = AssistantMemory(tmp_path / "asst")
    add = MemoryAddTool(memory=memory)
    search = MemorySearchTool(memory=memory)
    await add.execute({"content": "用户住在杭州", "category": "fact"})
    await add.execute({"content": "国庆行程去北京", "category": "fact", "branch": "chat-123"})

    both = await search.execute({"query": "北京", "branch": "chat-123"})
    assert both.success is True
    assert both.payload["count"] == 1
    assert "国庆行程去北京" in both.payload["records"][0]["content"]
    assert both.payload["records"][0]["branch"] == "chat-123"

    main = await search.execute({"query": "杭州"})
    assert main.payload["count"] == 1
    assert main.payload["records"][0]["content"] == "用户住在杭州"


def test_privacy_firewall_clause_renders_for_home_bound_role() -> None:
    role = RoleProfile(
        role="助手",
        goal="g",
        backstory="b",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
        extra={"assistant_home_path": "asst"},
    )
    out = PrivacyFirewallSection().render(
        role_profile=role,
        task="",
        awareness=None,
        manifest=None,
        tools=(),
        activated_skills=(),
    )
    assert "检索到不等于可透露" in out.text
    assert "side-chats" in out.text
    assert "跨会话隐私防火墙" in out.text


def test_privacy_firewall_is_empty_without_home() -> None:
    role = RoleProfile(
        role="助手",
        goal="g",
        backstory="b",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
    )
    out = PrivacyFirewallSection().render(
        role_profile=role,
        task="",
        awareness=None,
        manifest=None,
        tools=(),
        activated_skills=(),
    )
    assert out.text == ""
