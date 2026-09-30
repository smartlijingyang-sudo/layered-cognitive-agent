"""memory_explain expands one record without parsing the projection file."""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.contracts.atoms.enums.enums import MemoryCategory, MemoryLayer
from lca.contracts.models.core.conversation.memory import MemoryRecord
from lca.infrastructure.memory.assistant_memory import AssistantMemory
from lca.infrastructure.memory.contextfiles.domain.explain import (
    ExplainableRecord,
    explain_record,
)
from lca.infrastructure.tools.assistant.memory_tools import MemoryExplainTool


def _record(record_id: str, content: str) -> MemoryRecord:
    return MemoryRecord(
        record_id=record_id,
        content=content,
        memory_type=MemoryLayer.SEMANTIC,
        importance=0.8,
        category=MemoryCategory.FACT,
        dedupe_key=record_id,
        confidence=0.9,
        source_trace_id="trace-1",
        created_at_ms=1_750_000_000_000,
        metadata={"source": "user", "trigger": "用户更正城市", "quote": "我住在杭州"},
    )


def test_explain_record_stops_when_the_older_revision_is_absent() -> None:
    target = ExplainableRecord(
        record_id="new",
        body="现在的事实",
        kind="fact",
        revision_of="missing",
    )
    explained = explain_record(target, [target])
    assert explained.supersession_chain == ("new",)
    assert explained.attribution == "unspecified"


def test_assistant_memory_explains_the_supersession_chain(tmp_path: Path) -> None:
    memory = AssistantMemory(tmp_path / "asst")
    memory.upsert(_record("city-1", "用户住在上海"))
    memory.supersede("city-1", _record("city-2", "用户住在杭州"))
    explained = memory.explain("city-2")
    assert explained is not None
    assert explained.claim == "用户住在杭州"
    assert explained.kind == "fact"
    assert explained.salience == 0.9
    assert explained.attribution == "user"
    assert explained.quote == "我住在杭州"
    assert explained.confidence == 0.9
    assert "用户更正城市" in explained.timeline
    assert explained.supersession_chain[0] == "city-2"
    assert "city-1" in explained.supersession_chain
    assert memory.explain("missing") is None


@pytest.mark.asyncio
async def test_memory_explain_tool_returns_the_eight_fields(tmp_path: Path) -> None:
    memory = AssistantMemory(tmp_path / "asst")
    memory.upsert(_record("city-1", "用户住在上海"))
    observation = await MemoryExplainTool(memory=memory).execute({"record_id": "city-1"})
    assert observation.success is True
    payload = observation.payload
    assert payload["claim"] == "用户住在上海"
    assert payload["kind"] == "fact"
    assert payload["supersession_chain"] == ["city-1"]
    missing = await MemoryExplainTool(memory=memory).execute({"record_id": "nope"})
    assert missing.success is False
