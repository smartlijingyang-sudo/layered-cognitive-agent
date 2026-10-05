"""memory_search 合并索引与实时存储，两者都不完整。

索引是投影，只有 ``run_dream`` 做全量重建，所以它可能装着实时存储看不到的流水
行，也可能缺上一次重建之后写入的语义记录。``execute`` 原先在索引存在时完全跳过
``_search_main``，于是一个只含流水的索引会把实时语义记录整体藏起来。Task 3 之后
每个助理每轮都写流水，这个洞是普遍可达的。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.contracts.atoms.enums.enums import MemoryCategory, MemoryLayer
from lca.contracts.models.core.conversation.memory import MemoryRecord
from lca.infrastructure.memory.assistant_memory import AssistantMemory
from lca.infrastructure.memory.contextfiles.adapters.disk import DiskFileStore
from lca.infrastructure.memory.contextfiles.service.indexing import (
    build_memory_index,
    index_trail_line,
)
from lca.infrastructure.tools.assistant.memory_tools import MemorySearchTool

_SEMANTIC = "用户偏好简洁的回复"
_TRAIL_LINE = "还是简洁一点好"
_DATE = "2026-10-05"


def _memory_with_semantic(home: Path) -> AssistantMemory:
    (home / "memory").mkdir(parents=True, exist_ok=True)
    memory = AssistantMemory(home)
    memory.upsert(
        MemoryRecord(
            record_id="mem_verbosity",
            content=_SEMANTIC,
            memory_type=MemoryLayer.SEMANTIC,
            importance=0.9,
            category=MemoryCategory.PREFERENCE,
            dedupe_key="preference:verbosity",
            confidence=1.0,
            metadata={"source": "user"},
        )
    )
    return memory


def _append_trail(home: Path, line: str) -> None:
    path = home / "memory" / f"{_DATE}.md"
    existing = path.read_text(encoding="utf-8") if path.is_file() else f"# {_DATE}\n\n"
    path.write_text(f"{existing}- {line}\n", encoding="utf-8")


def _contents(rows: list) -> list[str]:
    return [str(row.get("content") or "") for row in rows]


@pytest.mark.asyncio
async def test_trail_only_index_does_not_hide_live_semantic(tmp_path: Path) -> None:
    """回归锁：增量索引出现后，实时语义记录必须仍然可检索。"""
    home = tmp_path / "asst"
    memory = _memory_with_semantic(home)
    _append_trail(home, _TRAIL_LINE)
    assert index_trail_line(home, _DATE, _TRAIL_LINE) is True

    observation = await MemorySearchTool(memory=memory).execute({"query": "简洁", "limit": 10})

    contents = _contents((observation.payload or {}).get("records") or [])
    assert any(_SEMANTIC in c for c in contents)
    assert any(_TRAIL_LINE in c for c in contents)


@pytest.mark.asyncio
async def test_complete_index_does_not_duplicate_a_semantic_record(tmp_path: Path) -> None:
    """全量索引里语义文档与实时存储指向同一条记录，合并后只出现一次。"""
    home = tmp_path / "asst"
    memory = _memory_with_semantic(home)
    build_memory_index(home, DiskFileStore(home), memory.query(MemoryLayer.SEMANTIC))

    observation = await MemorySearchTool(memory=memory).execute({"query": "简洁", "limit": 10})

    rows = (observation.payload or {}).get("records") or []
    matching = [row for row in rows if _SEMANTIC in str(row.get("content") or "")]
    assert len(matching) == 1


@pytest.mark.asyncio
async def test_without_any_index_the_live_store_still_answers(tmp_path: Path) -> None:
    home = tmp_path / "asst"
    memory = _memory_with_semantic(home)

    observation = await MemorySearchTool(memory=memory).execute({"query": "简洁", "limit": 10})

    assert _SEMANTIC in _contents((observation.payload or {}).get("records") or [])


@pytest.mark.asyncio
async def test_limit_still_caps_the_merged_result(tmp_path: Path) -> None:
    home = tmp_path / "asst"
    memory = _memory_with_semantic(home)
    _append_trail(home, _TRAIL_LINE)
    index_trail_line(home, _DATE, _TRAIL_LINE)

    observation = await MemorySearchTool(memory=memory).execute({"query": "简洁", "limit": 1})

    rows = (observation.payload or {}).get("records") or []
    assert len(rows) == 1
    assert (observation.payload or {}).get("count") == 1
