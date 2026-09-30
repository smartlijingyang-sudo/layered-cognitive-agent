"""Person pages are the record. The index is rebuilt from those pages."""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.infrastructure.memory.assistant_memory import AssistantMemory
from lca.infrastructure.memory.contextfiles.adapters.disk import DiskFileStore
from lca.infrastructure.memory.contextfiles.domain.people import slug_for
from lca.infrastructure.memory.contextfiles.events.publisher import (
    InProcessEventPublisher,
    PersonRecorded,
)
from lca.infrastructure.memory.contextfiles.service.people import PeopleDirectory
from lca.infrastructure.tools.assistant.memory_tools import PersonNoteTool


def test_slug_rejects_a_path() -> None:
    with pytest.raises(ValueError):
        slug_for("../outside")


def test_upsert_writes_the_page_and_rebuilds_the_index(tmp_path: Path) -> None:
    publisher = InProcessEventPublisher()
    events: list[object] = []
    publisher.subscribe(events.append)
    directory = PeopleDirectory(DiskFileStore(tmp_path), publisher)
    directory.upsert("王安", "喜欢短回复")
    directory.upsert("李雷", "住在杭州")
    directory.upsert("李雷", "住在北京")
    page = (tmp_path / "memory" / "people" / "李雷.md").read_text(encoding="utf-8")
    index = (tmp_path / "memory" / "people" / "INDEX.md").read_text(encoding="utf-8")
    assert "住在北京" in page
    assert "住在杭州" not in page
    assert index.index("李雷") < index.index("王安")
    assert index.count("- [李雷](李雷.md)") == 1
    assert [event.slug for event in events if isinstance(event, PersonRecorded)] == [
        "王安",
        "李雷",
        "李雷",
    ]


@pytest.mark.asyncio
async def test_person_note_tool_writes_under_the_assistant_home(tmp_path: Path) -> None:
    memory = AssistantMemory(tmp_path / "asst")
    observation = await PersonNoteTool(memory=memory).execute({"name": "李雷", "note": "住在杭州"})
    assert observation.success is True
    text = (tmp_path / "asst" / "memory" / "people" / "李雷.md").read_text(encoding="utf-8")
    assert "住在杭州" in text
    assert observation.payload["path"] == "memory/people/李雷.md"
    missing = await PersonNoteTool(memory=memory).execute({"name": "李雷", "note": "  "})
    assert missing.success is False
