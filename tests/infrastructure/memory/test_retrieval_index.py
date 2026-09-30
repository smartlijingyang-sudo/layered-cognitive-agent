"""Retrieval decision tree + FTS index over curated memory and trail files."""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.contracts.atoms.enums.enums import MemoryCategory, MemoryLayer
from lca.contracts.models.core.conversation.memory import MemoryRecord
from lca.contracts.models.team.role.team import RoleProfile, ToolPermissionManifest
from lca.infrastructure.memory.assistant_memory import AssistantMemory
from lca.infrastructure.memory.contextfiles.adapters.disk import DiskFileStore
from lca.infrastructure.memory.contextfiles.service.indexing import build_memory_index
from lca.infrastructure.tools.assistant.memory_tools import MemorySearchTool
from lca.plugins.prompts.sections.memory import MemoryRetrievalSection


def _seed_memory(tmp_path: Path) -> AssistantMemory:
    memory = AssistantMemory(tmp_path / "asst")
    memory.upsert(
        MemoryRecord(
            record_id="city-1",
            content="用户住在杭州",
            memory_type=MemoryLayer.SEMANTIC,
            importance=0.9,
            category=MemoryCategory.FACT,
            dedupe_key="city",
            confidence=1.0,
            metadata={"source": "user"},
        )
    )
    return memory


def test_build_index_from_curated_and_trail(tmp_path: Path) -> None:
    memory = _seed_memory(tmp_path)
    trail_dir = tmp_path / "asst" / "memory"
    trail_dir.mkdir(parents=True, exist_ok=True)
    (trail_dir / "2026-09-30.md").write_text("# 2026-09-30\n\n- 项目下周发布\n", encoding="utf-8")
    count = build_memory_index(
        tmp_path / "asst",
        DiskFileStore(tmp_path / "asst"),
        memory.query(MemoryLayer.SEMANTIC),
    )
    assert count == 2
    assert (tmp_path / "asst" / "memory" / "index" / "fts.sqlite3").is_file()


@pytest.mark.asyncio
async def test_memory_search_queries_the_index(tmp_path: Path) -> None:
    memory = _seed_memory(tmp_path)
    build_memory_index(
        tmp_path / "asst",
        DiskFileStore(tmp_path / "asst"),
        memory.query(MemoryLayer.SEMANTIC),
    )
    search = MemorySearchTool(memory=memory)
    obs = await search.execute({"query": "杭州"})
    assert obs.success is True
    assert obs.payload["count"] == 1
    assert obs.payload["records"][0]["content"] == "用户住在杭州"


@pytest.mark.asyncio
async def test_memory_search_falls_back_without_index(tmp_path: Path) -> None:
    memory = _seed_memory(tmp_path)
    search = MemorySearchTool(memory=memory)
    obs = await search.execute({"query": "杭州"})
    assert obs.success is True
    assert obs.payload["count"] == 1


def test_retrieval_decision_tree_renders_for_home_bound_role() -> None:
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
    assert "memory_search" in out.text
    assert "多角度查询" in out.text
    assert "兜底" in out.text
    assert "绝不凭空编造事实" in out.text
    assert "记忆检索义务" in out.text
