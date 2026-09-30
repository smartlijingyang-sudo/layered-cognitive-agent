"""Scenario: cross-topic reminding across main memory and a side chat.

A substantive request about a topic must retrieve both the main memory fact
and the branch fact through the shipped ``memory_search`` routing, and the
assembled prompt carries the multi-query retrieval duty.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.contracts.models.team.role.team import RoleProfile, ToolPermissionManifest
from lca.infrastructure.memory.assistant_memory import AssistantMemory
from lca.infrastructure.tools.assistant.memory_tools import MemoryAddTool, MemorySearchTool
from lca.plugins.prompts.sections.memory import MemoryRetrievalSection


@pytest.mark.asyncio
async def test_cross_topic_search_returns_main_and_branch(tmp_path: Path) -> None:
    memory = AssistantMemory(tmp_path / "asst")
    add = MemoryAddTool(memory=memory)
    search = MemorySearchTool(memory=memory)
    await add.execute({"content": "用户负责支付系统", "category": "fact"})
    await add.execute({"content": "支付系统 10 月 1 日上线", "category": "fact", "branch": "pay-1"})

    result = await search.execute({"query": "支付", "branch": "pay-1"})
    contents = [r["content"] for r in result.payload["records"]]
    assert any("用户负责支付系统" in c for c in contents)
    assert any("支付系统 10 月 1 日上线" in c for c in contents)


def test_retrieval_duty_prompt_requires_multi_query() -> None:
    role = RoleProfile(
        role="助手",
        goal="g",
        backstory="b",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
        extra={"assistant_home_path": "asst"},
    )
    out = MemoryRetrievalSection().render(
        role_profile=role,
        task="",
        awareness=None,
        manifest=None,
        tools=(),
        activated_skills=(),
    )
    assert "至少 3 个角度" in out.text
    assert "扫描常驻记忆文件兜底" in out.text
