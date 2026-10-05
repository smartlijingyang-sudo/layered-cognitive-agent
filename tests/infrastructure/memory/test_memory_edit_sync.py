"""Unit tests for MemoryEditSyncService (Markdown edit event parser & writeback).

Validates INV-MEM-04 (ADD / SUPERSEDE / DELETE actions) and INV-MEM-05 (roundtrip invariance).
"""

from __future__ import annotations

from pathlib import Path

from lca.contracts.atoms.enums.enums import MemoryCategory, MemoryLayer
from lca.contracts.models.core.conversation.memory import MemoryRecord
from lca.infrastructure.memory.assistant_memory import AssistantMemory
from lca.infrastructure.memory.contextfiles.sync import MemoryEditSyncService


def _record(
    *,
    record_id: str,
    content: str,
    category: MemoryCategory = MemoryCategory.FACT,
) -> MemoryRecord:
    return MemoryRecord(
        record_id=record_id,
        content=content,
        memory_type=MemoryLayer.SEMANTIC,
        importance=0.9,
        category=category,
        dedupe_key=record_id,
        confidence=1.0,
        metadata={"source": "user"},
    )


def test_memory_edit_sync_add_supersede_delete(tmp_path: Path):
    """INV-MEM-04: Test ADD (no ID), SUPERSEDE (changed text with ID), and DELETE (missing ID)."""
    home = tmp_path / "asst_1"
    memory = AssistantMemory(home)
    sync = MemoryEditSyncService(memory)

    # 1. ADD initial markdown with no embedded IDs
    initial_md = """# 长期记忆

## Preferences
- 喜欢简洁回答

## Facts
- 部署在内网服务器
"""
    sync.apply_markdown_edit(initial_md)
    active = [r for r in memory.query(MemoryLayer.SEMANTIC) if not r.deleted]
    assert len(active) == 2
    contents = {r.content for r in active}
    assert "喜欢简洁回答" in contents
    assert "部署在内网服务器" in contents

    # 2. Get projected markdown from disk, which now carries embedded IDs
    projected = (home / "MEMORY.md").read_text(encoding="utf-8")
    assert "<!-- id:mem_" in projected

    # 3. Simulate user edit:
    # - Modify "喜欢简洁回答" -> "极其喜欢简洁回答" (SUPERSEDE)
    # - Delete "部署在内网服务器" (DELETE)
    # - Add new fact "主用数据库是 PostgreSQL" (ADD)
    lines = projected.splitlines()
    edited_lines = []
    for line in lines:
        if "部署在内网服务器" in line:
            continue  # deleted
        if "喜欢简洁回答" in line:
            edited_lines.append(line.replace("喜欢简洁回答", "极其喜欢简洁回答"))
        else:
            edited_lines.append(line)
    edited_lines.append("- 主用数据库是 PostgreSQL")

    sync.apply_markdown_edit("\n".join(edited_lines))

    updated_active = [r for r in memory.query(MemoryLayer.SEMANTIC) if not r.deleted]
    updated_contents = {r.content for r in updated_active}
    assert "极其喜欢简洁回答" in updated_contents
    assert "主用数据库是 PostgreSQL" in updated_contents
    assert "部署在内网服务器" not in updated_contents
    assert len(updated_active) == 2


def test_memory_edit_sync_roundtrip_idempotent(tmp_path: Path):
    """INV-MEM-05: Submitting unedited projection does not mutate semantic records."""
    home = tmp_path / "asst_2"
    memory = AssistantMemory(home)
    memory.upsert(_record(record_id="fact_1", content="已配置开发环境", category=MemoryCategory.FACT))
    memory.upsert(_record(record_id="pref_1", content="偏好英文输出", category=MemoryCategory.PREFERENCE))

    sync = MemoryEditSyncService(memory)
    projected = (home / "MEMORY.md").read_text(encoding="utf-8")

    # Re-apply projected content directly
    changes = sync.apply_markdown_edit(projected)
    assert changes["added"] == 0
    assert changes["superseded"] == 0
    assert changes["deleted"] == 0

    active = [r for r in memory.query(MemoryLayer.SEMANTIC) if not r.deleted]
    assert len(active) == 2
    assert {r.record_id for r in active} == {"fact_1", "pref_1"}
