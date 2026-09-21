"""PR-6（ADR-0246）：add → search → update → remove 记忆工具全流程。"""

from __future__ import annotations

import pytest

from lca.infrastructure.memory.assistant_memory import AssistantMemory
from lca.infrastructure.tools.assistant.memory_tools import (
    MemoryAddTool,
    MemoryRemoveTool,
    MemorySearchTool,
    MemoryUpdateTool,
)


@pytest.mark.asyncio
async def test_memory_tools_roundtrip(tmp_path) -> None:
    memory = AssistantMemory(tmp_path / "asst")
    add = MemoryAddTool(memory=memory)
    search = MemorySearchTool(memory=memory)
    update = MemoryUpdateTool(memory=memory)
    remove = MemoryRemoveTool(memory=memory)

    # add
    add_obs = await add.execute(
        {"content": "用户身份：架构师", "category": "identity", "dedupe_key": "identity:architect"}
    )
    assert add_obs.success is True
    record_id = add_obs.payload["record_id"]

    # search finds it
    search_obs = await search.execute({"query": "架构师", "limit": 5})
    assert search_obs.success is True
    assert search_obs.payload["count"] == 1
    assert search_obs.payload["records"][0]["record_id"] == record_id

    # update supersedes it
    update_obs = await update.execute(
        {"record_id": record_id, "content": "用户身份：高级架构师", "category": "identity"}
    )
    assert update_obs.success is True
    new_id = update_obs.payload["record_id"]
    assert update_obs.payload["supersedes"] == record_id

    # search returns the new fact, not the old
    search_obs2 = await search.execute({"query": "高级架构师"})
    assert search_obs2.payload["count"] == 1
    assert search_obs2.payload["records"][0]["record_id"] == new_id

    # remove (with confirmation) deletes it
    remove_obs = await remove.execute({"record_id": new_id, "confirmed": True})
    assert remove_obs.success is True
    search_obs3 = await search.execute({"query": "高级架构师"})
    assert search_obs3.payload["count"] == 0


@pytest.mark.asyncio
async def test_add_same_dedupe_key_supersedes(tmp_path) -> None:
    memory = AssistantMemory(tmp_path / "asst")
    add = MemoryAddTool(memory=memory)
    search = MemorySearchTool(memory=memory)

    await add.execute(
        {"content": "用户身份：架构师", "category": "identity", "dedupe_key": "identity:architect"}
    )
    obs2 = await add.execute(
        {
            "content": "用户身份：高级架构师",
            "category": "identity",
            "dedupe_key": "identity:architect",
        }
    )

    results = (await search.execute({"query": "架构师"})).payload["records"]
    # 同 dedupe_key 只保留最新一条
    assert len(results) == 1
    assert results[0]["record_id"] == obs2.payload["record_id"]


@pytest.mark.asyncio
async def test_multi_term_search(tmp_path) -> None:
    memory = AssistantMemory(tmp_path / "asst")
    add = MemoryAddTool(memory=memory)
    search = MemorySearchTool(memory=memory)

    await add.execute(
        {"content": "用户姓名：李超", "category": "identity", "dedupe_key": "identity:name"}
    )
    await add.execute(
        {
            "content": "技术栈偏好：Rust 与 Python",
            "category": "preference",
            "dedupe_key": "preference:stack",
        }
    )
    await add.execute(
        {
            "content": "架构原则：简单可依赖",
            "category": "preference",
            "dedupe_key": "preference:arch",
        }
    )

    # 空格切分的多关键词复合搜索
    res = await search.execute({"query": "姓名 技术栈 架构", "limit": 10})
    assert res.success is True
    records = res.payload["records"]
    assert len(records) == 3
    contents = [r["content"] for r in records]
    assert "用户姓名：李超" in contents
    assert "技术栈偏好：Rust 与 Python" in contents
    assert "架构原则：简单可依赖" in contents
