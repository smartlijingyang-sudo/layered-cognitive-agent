"""Test the unified memory-tool context seam (INV-ARCH-13).

``_BaseMemoryTool`` exposes ``_file_store``, ``_layout``, ``_sidechat_dir``,
``_people_dir`` and ``_groups_dir`` derived from the assistant home, so derived
tools share one file-store/directory seam instead of constructing their own
stores per call. The seam must point at the tool's home and leak no state
across sessions.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from lca.infrastructure.memory.assistant_memory import AssistantMemory
from lca.infrastructure.memory.contextfiles.adapters.disk import DiskFileStore
from lca.infrastructure.memory.contextfiles.domain.layout import ContextLayout, packaged_layout
from lca.infrastructure.memory.contextfiles.service.groups import GroupsDirectory
from lca.infrastructure.memory.contextfiles.service.people import PeopleDirectory
from lca.infrastructure.memory.contextfiles.service.sidechat import SideChatDirectory
from lca.infrastructure.tools.assistant.memory_tools import (
    GroupNoteTool,
    MemoryAddTool,
    MemoryExplainTool,
    MemoryRemoveTool,
    MemorySearchTool,
    MemoryUpdateTool,
    PersonNoteTool,
    _BaseMemoryTool,
)

_ALL_TOOL_CLASSES = [
    MemorySearchTool,
    MemoryAddTool,
    MemoryUpdateTool,
    MemoryRemoveTool,
    MemoryExplainTool,
    PersonNoteTool,
    GroupNoteTool,
]


def test_inv_arch_13_base_tool_exposes_unified_seam_properties() -> None:
    """INV-ARCH-13: The five seam accessors are read-only properties."""
    for prop in ("_file_store", "_layout", "_sidechat_dir", "_people_dir", "_groups_dir"):
        assert isinstance(getattr(_BaseMemoryTool, prop, None), property), (
            f"missing property {prop}"
        )


@pytest.mark.parametrize("tool_cls", _ALL_TOOL_CLASSES)
def test_inv_arch_13_seam_points_at_tool_home(
    tool_cls: type[_BaseMemoryTool], tmp_path: Path
) -> None:
    """INV-ARCH-13: Every tool's seam properties resolve to its own assistant home."""
    home = tmp_path / "asst"
    tool = tool_cls(memory=AssistantMemory(home))

    assert isinstance(tool._file_store, DiskFileStore)
    assert tool._file_store.root == home.resolve()
    assert isinstance(tool._layout, ContextLayout)
    assert tool._layout == packaged_layout()
    assert isinstance(tool._sidechat_dir, SideChatDirectory)
    assert isinstance(tool._people_dir, PeopleDirectory)
    assert isinstance(tool._groups_dir, GroupsDirectory)


@pytest.mark.parametrize("tool_cls", _ALL_TOOL_CLASSES)
def test_inv_arch_13_no_state_leaks_across_sessions(
    tool_cls: type[_BaseMemoryTool], tmp_path: Path
) -> None:
    """INV-ARCH-13: Tools rooted at different homes point at different file stores."""
    tool_a = tool_cls(memory=AssistantMemory(tmp_path / "asst_a"))
    tool_b = tool_cls(memory=AssistantMemory(tmp_path / "asst_b"))

    assert tool_a._file_store.root == (tmp_path / "asst_a").resolve()
    assert tool_b._file_store.root == (tmp_path / "asst_b").resolve()
    assert tool_a._file_store.root != tool_b._file_store.root


def test_inv_arch_13_seam_drives_directory_writes(tmp_path: Path) -> None:
    """INV-ARCH-13: Person/group/side-chat writes through the seam land under the tool home."""
    home = tmp_path / "asst"
    tool = PersonNoteTool(memory=AssistantMemory(home))
    layout = tool._layout

    page = tool._people_dir.upsert("Alice", "LCA maintainer")
    assert (home / layout.person_page_path(page.slug)).is_file()

    group = tool._groups_dir.upsert("LCA", "core team")
    assert (home / layout.group_page_path(group.slug)).is_file()

    record = tool._sidechat_dir.write("chat-1", "branch fact")
    assert (home / layout.side_chat_memory_path("chat-1")).is_file()
    assert record.content == "branch fact"


def test_inv_arch_13_derived_tools_do_not_reconstruct_store_or_layout() -> None:
    """INV-ARCH-13: Only _BaseMemoryTool constructs DiskFileStore or layout_for_home."""
    from lca.infrastructure.tools.assistant import memory_tools as memory_tools_module

    source_path = Path(memory_tools_module.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))

    base_class: ast.ClassDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "_BaseMemoryTool":
            base_class = node
            break
    assert base_class is not None

    base_span = range(base_class.lineno, base_class.end_lineno + 1)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = (
                func.id
                if isinstance(func, ast.Name)
                else func.attr
                if isinstance(func, ast.Attribute)
                else None
            )
            if name in {"DiskFileStore", "layout_for_home"}:
                assert node.lineno in base_span, (
                    f"Derived tool constructs {name} directly at line {node.lineno}"
                )
