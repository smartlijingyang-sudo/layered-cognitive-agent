"""Group pages are the record. The index is rebuilt from those pages."""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.infrastructure.memory.assistant_memory import AssistantMemory
from lca.infrastructure.memory.contextfiles.adapters.disk import DiskFileStore
from lca.infrastructure.memory.contextfiles.events.publisher import (
    GroupRecorded,
    InProcessEventPublisher,
)
from lca.infrastructure.memory.contextfiles.service.groups import GroupsDirectory
from lca.infrastructure.tools.assistant.memory_tools import GroupNoteTool


def test_upsert_writes_the_page_and_rebuilds_the_index(tmp_path: Path) -> None:
    publisher = InProcessEventPublisher()
    events: list[object] = []
    publisher.subscribe(events.append)
    directory = GroupsDirectory(DiskFileStore(tmp_path), publisher)
    directory.upsert("设计组", "每周三同步")
    directory.upsert("产品组", "负责发布")
    directory.upsert("产品组", "负责发布和复盘")
    page = (tmp_path / "memory" / "groups" / "产品组.md").read_text(encoding="utf-8")
    index = (tmp_path / "memory" / "groups" / "INDEX.md").read_text(encoding="utf-8")
    assert "负责发布和复盘" in page
    assert "负责发布\n" not in page
    assert index.startswith("# 群体\n")
    assert "# 人物" not in index
    assert index.index("产品组") < index.index("设计组")
    assert index.count("- [产品组](产品组.md)") == 1
    assert not (tmp_path / "memory" / "people").exists()
    assert [event.slug for event in events if isinstance(event, GroupRecorded)] == [
        "设计组",
        "产品组",
        "产品组",
    ]


@pytest.mark.asyncio
async def test_group_note_tool_writes_under_the_assistant_home(tmp_path: Path) -> None:
    memory = AssistantMemory(tmp_path / "asst")
    observation = await GroupNoteTool(memory=memory).execute(
        {"name": "设计组", "note": "每周三同步"}
    )
    assert observation.success is True
    text = (tmp_path / "asst" / "memory" / "groups" / "设计组.md").read_text(encoding="utf-8")
    assert "每周三同步" in text
    assert observation.payload["path"] == "memory/groups/设计组.md"
    missing = await GroupNoteTool(memory=memory).execute({"name": "设计组", "note": "  "})
    assert missing.success is False
