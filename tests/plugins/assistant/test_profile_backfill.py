"""PR-5（ADR-0246）：identity 事实触发 USER.md 回填 + revision 快照。"""

from __future__ import annotations

import pytest

from lca.contracts.atoms.enums.enums import MemoryCategory, MemoryLayer, ReflectionVerdict
from lca.contracts.models.core.conversation.memory import MemoryRecord
from lca.contracts.models.core.execution.decision import Observation, Reflection
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.infrastructure.memory.assistant_memory import AssistantMemory
from lca.plugins.assistant.profile.profile import (
    ProfileBackfillService,
    make_backfill_callback,
)


class _RecordingCatalog:
    """记录 ``revise_profile`` 调用的 fake catalog。"""

    def __init__(self) -> None:
        self.revisions: list[tuple[str, object]] = []

    def revise_profile(self, assistant_id: str, patch: object) -> dict[str, int]:
        self.revisions.append((assistant_id, patch))
        return {"revision_seq": len(self.revisions)}


def _identity_record() -> MemoryRecord:
    return MemoryRecord(
        record_id="mem_1",
        content="用户身份：架构师",
        memory_type=MemoryLayer.SEMANTIC,
        importance=0.9,
        category=MemoryCategory.IDENTITY,
    )


def _preference_record() -> MemoryRecord:
    return MemoryRecord(
        record_id="mem_2",
        content="用户偏好：不喜欢啰嗦",
        memory_type=MemoryLayer.SEMANTIC,
        importance=0.9,
        category=MemoryCategory.PREFERENCE,
    )


def test_backfill_from_records_writes_user_md_patch() -> None:
    catalog = _RecordingCatalog()
    service = ProfileBackfillService(catalog)  # type: ignore[arg-type]
    revision = service.backfill_from_records("asst_1", [_identity_record(), _preference_record()])

    assert revision == {"revision_seq": 1}
    assert len(catalog.revisions) == 1
    assistant_id, patch = catalog.revisions[0]
    assert assistant_id == "asst_1"
    user_md = getattr(patch, "user_md", "")
    assert "## 身份" in user_md
    assert "用户身份：架构师" in user_md
    assert "## 偏好" in user_md
    assert "用户偏好：不喜欢啰嗦" in user_md


def test_backfill_noop_without_identity_or_preference() -> None:
    catalog = _RecordingCatalog()
    service = ProfileBackfillService(catalog)  # type: ignore[arg-type]
    fact = MemoryRecord(
        record_id="mem_3",
        content="一般事实",
        memory_type=MemoryLayer.SEMANTIC,
        importance=0.5,
        category=MemoryCategory.FACT,
    )
    result = service.backfill_from_records("asst_1", [fact])
    assert result is None
    assert catalog.revisions == []


def _state() -> AgentState:
    return AgentState(trace_id="trace_t", task="我是架构师", budget=Budget())


def _reflection() -> Reflection:
    return Reflection(
        reflection_id="refl_1",
        verdict=ReflectionVerdict.ON_TRACK,
        extra={
            "memory_candidates": [
                {
                    "category": MemoryCategory.IDENTITY.value,
                    "content": "用户身份：架构师",
                    "confidence": 1.0,
                    "source": "user",
                    "dedupe_key": "identity:architect",
                }
            ]
        },
    )


@pytest.mark.asyncio
async def test_assistant_memory_triggers_backfill_callback(tmp_path) -> None:
    catalog = _RecordingCatalog()
    callback = make_backfill_callback(catalog)  # type: ignore[arg-type]
    mem = AssistantMemory(tmp_path / "asst", profile_backfill=callback)
    await mem.update(
        _state(),
        Observation(observation_id="obs_1", success=True, payload=None),
        _reflection(),
    )

    assert len(catalog.revisions) == 1
    assistant_id, patch = catalog.revisions[0]
    assert assistant_id == "asst"
    assert "用户身份：架构师" in getattr(patch, "user_md", "")


@pytest.mark.asyncio
async def test_assistant_memory_without_callback_unchanged(tmp_path) -> None:
    catalog = _RecordingCatalog()
    mem = AssistantMemory(tmp_path / "asst")
    await mem.update(
        _state(),
        Observation(observation_id="obs_1", success=True, payload=None),
        _reflection(),
    )
    assert catalog.revisions == []
