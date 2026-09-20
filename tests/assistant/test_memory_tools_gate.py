"""PR-6（ADR-0246）：记忆工具边界闸门测试（敏感确认 + 输入校验）。"""

from __future__ import annotations

import pytest

from lca.infrastructure.memory.assistant_memory import AssistantMemory
from lca.infrastructure.tools.assistant.memory_tools import (
    MemoryAddTool,
    MemoryRemoveTool,
)


def _memory(tmp_path) -> AssistantMemory:
    return AssistantMemory(tmp_path / "asst")


@pytest.mark.asyncio
async def test_remove_requires_confirmation(tmp_path) -> None:
    tool = MemoryRemoveTool(memory=_memory(tmp_path))
    obs = await tool.execute({"record_id": "mem_1", "confirmed": False})
    assert obs.success is False
    assert "确认" in (obs.error or "")


@pytest.mark.asyncio
async def test_add_rejects_invalid_category(tmp_path) -> None:
    tool = MemoryAddTool(memory=_memory(tmp_path))
    obs = await tool.execute({"content": "用户身份：架构师", "category": "bogus"})
    assert obs.success is False
    assert "category" in (obs.error or "")


@pytest.mark.asyncio
async def test_add_rejects_empty_content(tmp_path) -> None:
    tool = MemoryAddTool(memory=_memory(tmp_path))
    obs = await tool.execute({"content": "", "category": "identity"})
    assert obs.success is False
    assert "content" in (obs.error or "")
