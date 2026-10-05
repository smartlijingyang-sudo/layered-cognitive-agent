"""D6 前提：24 小时调度上界成立，因为捕获当轮就可检索。

跨层场景。写侧是 cognition 的 ``record_turn_trail``，读侧是 infrastructure 的
``MemorySearchTool``，中间是增量索引。ADR-0287 §D6 接受 24 小时上界的条件是
偏好被捕获后当轮即可被 ADR-0260 C2 的强制检索命中，否则捕获到提升之间最长
24 小时既不进注入路径也搜不到。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.cognition.memory.daytime import record_turn_trail
from lca.contracts.atoms.enums.enums import MemoryCategory, MemoryLayer
from lca.contracts.models.core.conversation.memory import MemoryRecord
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.infrastructure.memory.assistant_memory import AssistantMemory
from lca.infrastructure.tools.assistant.memory_tools import MemorySearchTool

_NOW_MS = 1_759_200_000_000
_UTTERANCE = "还是简洁一点好"
_EXISTING = "用户姓名：Lee"


def _state(task: str) -> AgentState:
    return AgentState(trace_id="trace_d6", task=task, budget=Budget())


def _contents(rows: list) -> list[str]:
    return [str(row.get("content") or "") for row in rows]


@pytest.mark.asyncio
async def test_captured_preference_is_searchable_in_the_same_turn(tmp_path: Path) -> None:
    home = tmp_path / "asst"
    (home / "memory").mkdir(parents=True)
    memory = AssistantMemory(home)
    memory.upsert(
        MemoryRecord(
            record_id="mem_name",
            content=_EXISTING,
            memory_type=MemoryLayer.SEMANTIC,
            importance=0.9,
            category=MemoryCategory.IDENTITY,
            dedupe_key="identity:name",
            confidence=1.0,
            metadata={"source": "user"},
        )
    )
    tool = MemorySearchTool(memory=memory)

    assert record_turn_trail({"assistant_home_path": str(home)}, _state(_UTTERANCE), now_ms=_NOW_MS)

    captured = await tool.execute({"query": "简洁", "limit": 10})
    assert any(_UTTERANCE in c for c in _contents((captured.payload or {}).get("records") or []))

    still_there = await tool.execute({"query": "Lee", "limit": 10})
    assert any(_EXISTING in c for c in _contents((still_there.payload or {}).get("records") or []))
