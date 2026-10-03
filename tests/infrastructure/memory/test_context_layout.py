"""Context-file names and budgets come from TOML, including a home overlay."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from lca.contracts.atoms.enums.enums import MemoryCategory, MemoryLayer
from lca.contracts.models.core.conversation.memory import MemoryRecord
from lca.infrastructure.memory.assistant_memory import AssistantMemory
from lca.infrastructure.memory.contextfiles.adapters.disk import DiskFileStore
from lca.infrastructure.memory.contextfiles.domain.layout import (
    layout_for_home,
    merge_layout,
    packaged_layout,
    read_layout,
)
from lca.infrastructure.memory.contextfiles.domain.standing import render_injected
from lca.infrastructure.memory.contextfiles.service.assembly import refresh_standing_backstory
from lca.infrastructure.memory.contextfiles.service.compaction import preserve_standing_sections
from lca.infrastructure.memory.contextfiles.service.groups import GroupsDirectory
from lca.infrastructure.memory.contextfiles.service.people import PeopleDirectory
from lca.infrastructure.tools.assistant.memory_tools import GroupNoteTool, PersonNoteTool
from lca.plugins.assistant.persona.persona import persona_from_home

_REPO = Path(__file__).resolve().parents[3]


def _overlay(home: Path, text: str) -> None:
    target = home / "memory" / "contextfiles.toml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def test_packaged_layout_matches_the_toml_file() -> None:
    path = _REPO / "lca" / "infrastructure" / "memory" / "contextfiles" / "layout.toml"
    assert packaged_layout() == read_layout(path.read_text(encoding="utf-8"))


def test_python_sources_do_not_own_the_layout_names() -> None:
    root = _REPO / "lca" / "infrastructure" / "memory" / "contextfiles"
    standing = (root / "domain" / "standing.py").read_text(encoding="utf-8")
    people = (root / "service" / "people.py").read_text(encoding="utf-8")
    groups = (root / "service" / "groups.py").read_text(encoding="utf-8")
    assembly = (root / "service" / "assembly.py").read_text(encoding="utf-8")
    persona = (_REPO / "lca" / "plugins" / "assistant" / "persona" / "persona.py").read_text(
        encoding="utf-8"
    )
    tools = (
        _REPO / "lca" / "infrastructure" / "tools" / "assistant" / "memory_tools.py"
    ).read_text(encoding="utf-8")
    assert "SOUL.md" not in standing
    assert "memory/people" not in people
    assert "INDEX.md" not in people
    assert "memory/groups" not in groups
    assert "INDEX.md" not in groups
    assert "AGENTS.md" not in assembly
    assert "3000" not in assembly
    assert "SOUL.md" not in persona
    assert "3000" not in persona
    assert "memory/people" not in tools
    assert "memory/groups" not in tools


def test_read_layout_rejects_a_parent_segment() -> None:
    text = (_REPO / "lca" / "infrastructure" / "memory" / "contextfiles" / "layout.toml").read_text(
        encoding="utf-8"
    )
    broken = text.replace('people_dir = "memory/people"', 'people_dir = "../outside"')
    with pytest.raises(ValueError):
        read_layout(broken)
    broken_groups = text.replace('groups_dir = "memory/groups"', 'groups_dir = "../outside"')
    with pytest.raises(ValueError):
        read_layout(broken_groups)


def test_merge_rejects_unknown_keys() -> None:
    with pytest.raises(ValueError):
        merge_layout(packaged_layout(), "extra = 1\n")


def test_home_overlay_moves_people_and_the_tool_follows(tmp_path: Path) -> None:
    home = tmp_path / "asst"
    _overlay(home, 'people_dir = "notes/people"\npeople_index = "CATALOG.md"\n')
    directory = PeopleDirectory(DiskFileStore(home), layout=layout_for_home(home))
    directory.upsert("李雷", "住在杭州")
    page = home / "notes" / "people" / "李雷.md"
    index = home / "notes" / "people" / "CATALOG.md"
    assert "住在杭州" in page.read_text(encoding="utf-8")
    assert "李雷" in index.read_text(encoding="utf-8")
    assert not (home / "memory" / "people").exists()
    assert layout_for_home(home).groups_dir == "memory/groups"


def test_home_overlay_moves_groups(tmp_path: Path) -> None:
    home = tmp_path / "asst"
    _overlay(home, 'groups_dir = "notes/groups"\ngroups_index = "CATALOG.md"\n')
    directory = GroupsDirectory(DiskFileStore(home), layout=layout_for_home(home))
    directory.upsert("设计组", "每周三同步")
    page = home / "notes" / "groups" / "设计组.md"
    index = home / "notes" / "groups" / "CATALOG.md"
    assert "每周三同步" in page.read_text(encoding="utf-8")
    assert "设计组" in index.read_text(encoding="utf-8")
    assert not (home / "memory" / "groups").exists()
    assert layout_for_home(home).people_dir == "memory/people"


@pytest.mark.asyncio
async def test_group_note_tool_uses_the_home_overlay(tmp_path: Path) -> None:
    home = tmp_path / "asst"
    _overlay(home, 'groups_dir = "notes/groups"\n')
    observation = await GroupNoteTool(memory=AssistantMemory(home)).execute(
        {"name": "设计组", "note": "每周三同步"}
    )
    assert observation.success is True
    assert observation.payload == {
        "slug": "设计组",
        "name": "设计组",
        "path": "notes/groups/设计组.md",
    }
    assert (home / "notes" / "groups" / "设计组.md").is_file()


@pytest.mark.asyncio
async def test_person_note_tool_uses_the_home_overlay(tmp_path: Path) -> None:
    home = tmp_path / "asst"
    _overlay(home, 'people_dir = "notes/people"\n')
    observation = await PersonNoteTool(memory=AssistantMemory(home)).execute(
        {"name": "李雷", "note": "住在杭州"}
    )
    assert observation.success is True
    assert observation.payload == {
        "slug": "李雷",
        "name": "李雷",
        "path": "notes/people/李雷.md",
    }
    assert (home / "notes" / "people" / "李雷.md").is_file()


def test_home_overlay_changes_standing_order(tmp_path: Path) -> None:
    home = tmp_path / "asst"
    home.mkdir()
    _overlay(home, 'standing_files = ["TOOLS.md", "SOUL.md"]\n')
    (home / "SOUL.md").write_text("soul-body", encoding="utf-8")
    (home / "TOOLS.md").write_text("tools-body", encoding="utf-8")
    (home / "AGENTS.md").write_text("手册正文", encoding="utf-8")
    persona = persona_from_home(str(home))
    assert persona.backstory.index("tools-body") < persona.backstory.index("soul-body")
    assert "手册正文" not in persona.backstory
    refreshed = refresh_standing_backstory(str(home), "fallback")
    assert refreshed.index("tools-body") < refreshed.index("soul-body")


def test_home_overlay_shrinks_the_backstory_budget(tmp_path: Path) -> None:
    home = tmp_path / "asst"
    home.mkdir()
    _overlay(home, "backstory_budget_chars = 40\n")
    (home / "SOUL.md").write_text("字" * 500, encoding="utf-8")
    persona = persona_from_home(str(home))
    assert len(persona.backstory) <= 40
    assert "字" * 50 not in persona.backstory


def test_home_overlay_renames_the_agents_heading(tmp_path: Path) -> None:
    home = tmp_path / "asst"
    home.mkdir()
    _overlay(
        home,
        'standing_files = ["AGENTS.md"]\nagents_heading = "## 自定义约定"\n',
    )
    (home / "AGENTS.md").write_text("手册正文", encoding="utf-8")
    persona = persona_from_home(str(home))
    assert "## 自定义约定" in persona.backstory
    assert "工作约定" not in persona.backstory


def test_bad_overlay_is_ignored_and_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    home = tmp_path / "asst"
    home.mkdir()
    _overlay(home, 'people_dir = "/tmp/elsewhere"\n')
    (home / "SOUL.md").write_text("soul-text", encoding="utf-8")
    with caplog.at_level(
        logging.WARNING,
        logger="lca.infrastructure.memory.contextfiles.domain.layout",
    ):
        layout = layout_for_home(home)
    assert layout.people_dir == "memory/people"
    assert "context layout override ignored" in caplog.text
    assert "soul-text" in refresh_standing_backstory(str(home), "fallback")


def test_preserve_uses_the_supplied_layout(tmp_path: Path) -> None:
    layout = merge_layout(
        packaged_layout(),
        'standing_files = ["NOTES.md"]\nlive_note = "以这份为准。"\n',
    )
    (tmp_path / "NOTES.md").write_text("新笔记\n", encoding="utf-8")
    out = preserve_standing_sections(
        "规则\n" + render_injected("MEMORY.md", "旧记忆"),
        DiskFileStore(tmp_path),
        layout=layout,
    )
    assert "旧记忆" not in out
    assert "新笔记" in out
    assert "以这份为准。" in out
    assert packaged_layout().live_note not in out


def test_projection_file_comes_from_the_home_overlay(tmp_path: Path) -> None:
    home = tmp_path / "asst"
    _overlay(home, 'projection_file = "notes/FACTS.md"\n')
    memory = AssistantMemory(home)
    memory.upsert(
        MemoryRecord(
            record_id="city-1",
            content="用户住在杭州",
            memory_type=MemoryLayer.SEMANTIC,
            importance=0.5,
            category=MemoryCategory.FACT,
            dedupe_key="city-1",
            source_trace_id="trace-1",
            created_at_ms=1_750_000_000_000,
            metadata={"source": "user", "trigger": "用户要求记下"},
        )
    )
    projected = home / "notes" / "FACTS.md"
    assert "用户住在杭州" in projected.read_text(encoding="utf-8")
    assert not (home / "MEMORY.md").exists()
    assert memory.last_curated_receipt is not None
    assert memory.last_curated_receipt.path == str(projected)


def test_constitution_md_is_first_standing_file() -> None:
    layout = packaged_layout()
    assert layout.standing_files[0] == "CONSTITUTION.md"
    assert "CONSTITUTION.md" in layout.standing_files
