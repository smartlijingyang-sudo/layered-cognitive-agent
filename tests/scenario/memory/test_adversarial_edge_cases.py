"""Adversarial memory scenarios driven through the shipped write and reply gates.

These cases do not call a model. They assert the gates that make the five
spec scenarios hold: an unknown password is not in memory, an encoded
credential is rejected, a failed write cannot be acknowledged, a side chat
does not receive the main session's private note, and a later preference
supersedes the earlier one.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from lca.cognition.memory.acknowledgement import guard_reply
from lca.contracts.atoms.enums.enums import MemoryLayer
from lca.contracts.models.team.role.team import RoleProfile, ToolPermissionManifest
from lca.infrastructure.memory.assistant_memory import AssistantMemory
from lca.infrastructure.tools.assistant.memory_tools import (
    MemoryAddTool,
    MemoryExplainTool,
    MemorySearchTool,
)
from lca.plugins.prompts.sections.memory import (
    MemoryRetrievalSection,
    PrivacyFirewallSection,
)

_B64_KEY = "c2stcHJvai1hYmNkZWZnaGlqa2xtbm9wcXJzdHV2d3h5ejEyMzQ1Njc4OTA="


def _role() -> RoleProfile:
    return RoleProfile(
        role="助手",
        goal="g",
        backstory="b",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
        extra={"assistant_home_path": "asst"},
    )


def _render_retrieval() -> str:
    return (
        MemoryRetrievalSection()
        .render(
            role_profile=_role(),
            task="",
            awareness=None,
            manifest=None,
            tools=(),
            activated_skills=(),
        )
        .text
    )


@pytest.mark.asyncio
async def test_poisoned_password_is_absent_and_rejected(tmp_path: Path) -> None:
    memory = AssistantMemory(tmp_path / "asst")
    add = MemoryAddTool(memory=memory)
    search = MemorySearchTool(memory=memory)
    found = await search.execute({"query": "admin888"})
    assert found.payload["count"] == 0
    rejected = await add.execute(
        {"content": "数据库密码: admin888", "category": "fact", "dedupe_key": "secret:db"}
    )
    assert rejected.success is False
    assert rejected.error == "credential_rejected"
    assert memory.query(MemoryLayer.SEMANTIC) == []
    assert "绝不凭空编造" in _render_retrieval()
    projected = tmp_path / "asst" / "MEMORY.md"
    assert not projected.exists() or "admin888" not in projected.read_text(encoding="utf-8")
    runtime = SimpleNamespace(memory=memory)
    assert (
        guard_reply("已记下数据库密码。", runtime) == "这条还没有写入记忆文件。我不能说已经记下。"
    )


@pytest.mark.asyncio
async def test_base64_credential_is_rejected(tmp_path: Path) -> None:
    memory = AssistantMemory(tmp_path / "asst")
    obs = await MemoryAddTool(memory=memory).execute(
        {"content": f"测试环境标记 {_B64_KEY}", "category": "fact"}
    )
    assert obs.success is False
    assert obs.error == "credential_rejected"
    assert not (tmp_path / "asst" / "MEMORY.md").exists()
    spilled = [
        path.read_text(encoding="utf-8")
        for path in (tmp_path / "asst").rglob("*")
        if path.is_file()
    ]
    assert all(_B64_KEY not in text for text in spilled)


@pytest.mark.asyncio
async def test_unwritable_memory_dir_cannot_be_acknowledged(tmp_path: Path) -> None:
    if os.geteuid() == 0:
        pytest.skip("root bypasses directory permissions")
    home = tmp_path / "asst"
    memory = AssistantMemory(home)
    memory_dir = home / "memory"
    memory_dir.chmod(0o555)
    try:
        obs = await MemoryAddTool(memory=memory).execute(
            {"content": "上线时间推迟到周六上午 10 点", "category": "fact"}
        )
    finally:
        memory_dir.chmod(0o755)
    assert obs.success is False
    assert "记忆没有写入" in (obs.error or "")
    runtime = SimpleNamespace(memory=memory)
    assert guard_reply("好的，已记下。", runtime) == "这条还没有写入记忆文件。我不能说已经记下。"


@pytest.mark.asyncio
async def test_side_chat_search_does_not_copy_private_main_memory(tmp_path: Path) -> None:
    memory = AssistantMemory(tmp_path / "asst")
    add = MemoryAddTool(memory=memory)
    private = "李超的作息是每天 6 点起床，病史见主会话"
    await add.execute({"content": private, "category": "fact"})
    search = await MemorySearchTool(memory=memory).execute(
        {"query": "作息", "branch": "audit-room"}
    )
    assert search.success is True
    assert all(private not in row["content"] for row in search.payload["records"])
    branch = tmp_path / "asst" / "side-chats" / "audit-room" / "MEMORY.md"
    assert not branch.exists()
    firewall = (
        PrivacyFirewallSection()
        .render(
            role_profile=_role(),
            task="",
            awareness=None,
            manifest=None,
            tools=(),
            activated_skills=(),
        )
        .text
    )
    assert "检索到不等于可透露" in firewall
    assert "不得向外泄露" in firewall


@pytest.mark.asyncio
async def test_later_preference_supersedes_the_earlier_one(tmp_path: Path) -> None:
    memory = AssistantMemory(tmp_path / "asst")
    add = MemoryAddTool(memory=memory)
    first = await add.execute(
        {
            "content": "接口返回必须用 XML",
            "category": "preference",
            "dedupe_key": "preference:api_format",
        }
    )
    second = await add.execute(
        {
            "content": "接口返回必须用 JSON",
            "category": "preference",
            "dedupe_key": "preference:api_format",
        }
    )
    assert first.success is True
    assert second.success is True
    active = memory.query(MemoryLayer.SEMANTIC)
    assert len(active) == 1
    assert active[0].content == "接口返回必须用 JSON"
    explained = await MemoryExplainTool(memory=memory).execute(
        {"record_id": second.payload["record_id"]}
    )
    chain = explained.payload["supersession_chain"]
    assert second.payload["record_id"] == chain[0]
    assert first.payload["record_id"] in chain
    projected = (tmp_path / "asst" / "MEMORY.md").read_text(encoding="utf-8")
    assert "JSON" in projected
    assert "XML" not in projected
