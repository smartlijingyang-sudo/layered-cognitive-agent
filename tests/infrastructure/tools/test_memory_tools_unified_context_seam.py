"""Tests verifying unified context seam in _BaseMemoryTool (INV-ARCH-13)."""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.infrastructure.memory.assistant_memory import AssistantMemory
from lca.infrastructure.memory.contextfiles.adapters.disk import DiskFileStore
from lca.infrastructure.memory.contextfiles.domain.layout import layout_for_home
from lca.infrastructure.memory.contextfiles.service.groups import GroupsDirectory
from lca.infrastructure.memory.contextfiles.service.people import PeopleDirectory
from lca.infrastructure.memory.contextfiles.service.sidechat import SideChatDirectory
from lca.infrastructure.tools.assistant.memory_tools import (
    GroupNoteTool,
    MemoryAddTool,
    MemorySearchTool,
    PersonNoteTool,
    _BaseMemoryTool,
)


def test_inv_arch_13_base_memory_tool_exposes_context_properties(tmp_path: Path) -> None:
    """INV-ARCH-13: _BaseMemoryTool provides cohesive directory and filestore properties."""
    memory = AssistantMemory(home_path=tmp_path)
    tool = _BaseMemoryTool(memory=memory)

    assert isinstance(tool._file_store, DiskFileStore)
    assert tool._file_store.root == tmp_path
    assert isinstance(tool._sidechat_dir, SideChatDirectory)
    assert isinstance(tool._people_dir, PeopleDirectory)
    assert isinstance(tool._groups_dir, GroupsDirectory)


@pytest.mark.asyncio
async def test_inv_arch_13_derived_tools_reuse_context_properties(tmp_path: Path) -> None:
    """INV-ARCH-13: Derived tools leverage the base properties to read/write context files without ad-hoc instantiation."""
    memory = AssistantMemory(home_path=tmp_path)
    layout = layout_for_home(tmp_path)

    # 1. PersonNoteTool writes via _people_dir
    person_tool = PersonNoteTool(memory=memory)
    res_person = await person_tool.execute({"name": "Alice Architecture", "note": "Chief Architect"})
    assert res_person.success is True
    assert res_person.payload is not None
    assert res_person.payload["name"] == "Alice Architecture"
    assert (tmp_path / layout.person_page_path(res_person.payload["slug"])).exists()

    # 2. GroupNoteTool writes via _groups_dir
    group_tool = GroupNoteTool(memory=memory)
    res_group = await group_tool.execute({"name": "Core Platform", "note": "Handles kernel & transport"})
    assert res_group.success is True
    assert res_group.payload is not None
    assert res_group.payload["name"] == "Core Platform"
    assert (tmp_path / layout.group_page_path(res_group.payload["slug"])).exists()

    # 3. MemoryAddTool writes branch via _sidechat_dir
    add_tool = MemoryAddTool(memory=memory)
    res_add = await add_tool.execute({
        "content": "Branch specific note",
        "category": "fact",
        "branch": "branch-alpha",
    })
    assert res_add.success is True
    assert (tmp_path / layout.side_chat_memory_path("branch-alpha")).exists()

    # 4. MemorySearchTool searches branch via _sidechat_dir
    search_tool = MemorySearchTool(memory=memory)
    res_search = await search_tool.execute({
        "query": "Branch",
        "branch": "branch-alpha",
    })
    assert res_search.success is True
    assert res_search.payload is not None
    assert res_search.payload["count"] >= 1
