"""memory_search 的索引路径与回退路径都过滤私人信息。

``MemorySearchTool.execute`` 原先只在 ``branch is not None`` 的分支过滤，
``_search_indexed`` 与 else 分支的 ``_search_main`` 直接返回。索引今天只装着经
``contains_secret`` 写入的 curated 记录，所以缺口不可达；trail 开始承载原始话轮
后，未过滤的用户原文会经索引进入模型上下文。写入方与这个过滤同一个 PR 落地。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.contracts.atoms.enums.enums import MemoryCategory, MemoryLayer
from lca.contracts.models.core.conversation.memory import MemoryRecord
from lca.infrastructure.memory.assistant_memory import AssistantMemory
from lca.infrastructure.memory.contextfiles.adapters.disk import DiskFileStore
from lca.infrastructure.memory.contextfiles.service.indexing import build_memory_index
from lca.infrastructure.tools.assistant.memory_tools import MemorySearchTool

_PRIVATE = "用户手机号是 13800138000"
_PUBLIC = "用户偏好简洁的回复"


def _seed(home: Path, *, index: bool) -> MemorySearchTool:
    (home / "memory").mkdir(parents=True, exist_ok=True)
    memory = AssistantMemory(home)
    for content, key in ((_PRIVATE, "fact:phone"), (_PUBLIC, "preference:verbosity")):
        memory.upsert(
            MemoryRecord(
                record_id=f"mem_{key}",
                content=content,
                memory_type=MemoryLayer.SEMANTIC,
                importance=0.9,
                category=MemoryCategory.FACT,
                dedupe_key=key,
                confidence=1.0,
                metadata={"source": "user"},
            )
        )
    if index:
        build_memory_index(home, DiskFileStore(home), memory.query(MemoryLayer.SEMANTIC))
    return MemorySearchTool(memory=memory)


def _contents(rows: list) -> list[str]:
    return [str(row.get("content") or "") for row in rows]


@pytest.mark.asyncio
async def test_indexed_path_drops_private_personal_rows(tmp_path: Path) -> None:
    tool = _seed(tmp_path / "asst", index=True)

    observation = await tool.execute({"query": "用户", "limit": 10})

    assert observation.success
    rows = (observation.payload or {}).get("records") or []
    assert _PUBLIC in _contents(rows)
    assert all("13800138000" not in content for content in _contents(rows))


@pytest.mark.asyncio
async def test_unindexed_fallback_drops_private_personal_rows(tmp_path: Path) -> None:
    """没有索引时 execute 回退到 _search_main，同一条过滤必须生效。"""
    tool = _seed(tmp_path / "asst", index=False)

    observation = await tool.execute({"query": "用户", "limit": 10})

    assert observation.success
    rows = (observation.payload or {}).get("records") or []
    assert _PUBLIC in _contents(rows)
    assert all("13800138000" not in content for content in _contents(rows))


@pytest.mark.asyncio
async def test_non_private_rows_survive_both_paths(tmp_path: Path) -> None:
    """过滤不能连带吃掉正常记录。"""
    indexed = _seed(tmp_path / "indexed", index=True)
    plain = _seed(tmp_path / "plain", index=False)

    for tool in (indexed, plain):
        observation = await tool.execute({"query": "简洁", "limit": 10})
        assert observation.success
        rows = (observation.payload or {}).get("records") or []
        assert _PUBLIC in _contents(rows)
