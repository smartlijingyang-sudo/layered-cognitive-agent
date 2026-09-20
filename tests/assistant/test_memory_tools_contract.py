"""PR-6（ADR-0246）：记忆工具族契约测试。"""

from __future__ import annotations

from lca.infrastructure.memory.assistant_memory import AssistantMemory
from lca.infrastructure.tools.assistant.memory_tools import (
    MemoryAddTool,
    MemoryRemoveTool,
    MemorySearchTool,
    MemoryUpdateTool,
)


def _memory(tmp_path) -> AssistantMemory:
    return AssistantMemory(tmp_path / "asst")


def test_four_tools_expose_stable_names() -> None:
    assert MemorySearchTool.name == "memory_search"
    assert MemoryAddTool.name == "memory_add"
    assert MemoryUpdateTool.name == "memory_update"
    assert MemoryRemoveTool.name == "memory_remove"


def test_tools_declare_parameters_schema(tmp_path) -> None:
    search = MemorySearchTool(memory=_memory(tmp_path))
    assert search.parameters["required"] == ["query"]
    assert "limit" in search.parameters["properties"]

    add = MemoryAddTool(memory=_memory(tmp_path))
    assert add.parameters["required"] == ["content", "category"]
    assert add.parameters["properties"]["category"]["enum"] == [
        "identity",
        "preference",
        "fact",
    ]

    update = MemoryUpdateTool(memory=_memory(tmp_path))
    assert update.parameters["required"] == ["record_id", "content"]

    remove = MemoryRemoveTool(memory=_memory(tmp_path))
    assert remove.parameters["required"] == ["record_id", "confirmed"]


def test_tools_are_not_idempotent_and_have_timeout(tmp_path) -> None:
    for tool in (
        MemorySearchTool(memory=_memory(tmp_path)),
        MemoryAddTool(memory=_memory(tmp_path)),
        MemoryUpdateTool(memory=_memory(tmp_path)),
        MemoryRemoveTool(memory=_memory(tmp_path)),
    ):
        assert tool.is_idempotent is False
        assert tool.default_timeout_s > 0
