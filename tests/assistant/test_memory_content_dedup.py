"""ADR-0247 回归：memory_add 与自动提取路径写入同一事实时，内容级去重收敛为一条活跃记录。

流程测试发现：模型经 ``memory_add`` 写入的 dedupe_key（如 ``user_identity``）与
``reflect.memory.extract`` 产出的 canonical dedupe_key（如 ``identity:architect``）
不同，导致同一事实两条活跃记录。本测试锁定 store 边界的内容级幂等。
"""

from __future__ import annotations

import pytest

from lca.contracts.atoms.enums.enums import MemoryCategory, MemoryLayer, ReflectionVerdict
from lca.contracts.models.core.conversation.memory import MemoryRecord
from lca.contracts.models.core.execution.decision import Observation, Reflection
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.infrastructure.memory.assistant_memory import AssistantMemory


def _state() -> AgentState:
    return AgentState(trace_id="trace_t", task="我是架构师", budget=Budget())


def _reflection(candidates: list[dict[str, object]]) -> Reflection:
    return Reflection(
        reflection_id="refl_1",
        verdict=ReflectionVerdict.ON_TRACK,
        extra={"memory_candidates": candidates},
    )


def _identity_record() -> MemoryRecord:
    return MemoryRecord(
        record_id="mem_add_1",
        content="用户身份：架构师",
        memory_type=MemoryLayer.SEMANTIC,
        importance=0.9,
        category=MemoryCategory.IDENTITY,
        dedupe_key="user_identity",
        confidence=1.0,
        metadata={"source": "user"},
    )


@pytest.mark.asyncio
async def test_memory_add_then_auto_extract_converges_to_single_identity(tmp_path) -> None:
    memory = AssistantMemory(tmp_path / "asst")

    # 模型经 memory_add 先写入（dedupe_key 与自动提取不同）
    memory.upsert(_identity_record())

    # 自动提取路径随后写入同一事实（canonical dedupe_key）
    await memory.update(
        _state(),
        Observation(observation_id="obs_1", success=True, payload=None),
        _reflection(
            [
                {
                    "category": MemoryCategory.IDENTITY.value,
                    "content": "用户身份：架构师",
                    "confidence": 1.0,
                    "source": "model",
                    "dedupe_key": "identity:architect",
                }
            ]
        ),
    )

    active = memory.query(MemoryLayer.SEMANTIC)
    assert len(active) == 1
    assert active[0].content == "用户身份：架构师"


@pytest.mark.asyncio
async def test_preference_phrasing_variants_converge(tmp_path) -> None:
    memory = AssistantMemory(tmp_path / "asst")

    memory.upsert(
        MemoryRecord(
            record_id="mem_add_2",
            content='称呼偏好：称呼用户为"老板"',
            memory_type=MemoryLayer.SEMANTIC,
            importance=0.9,
            category=MemoryCategory.PREFERENCE,
            dedupe_key="user_address_preference",
            confidence=1.0,
            metadata={"source": "user"},
        )
    )
    await memory.update(
        _state(),
        Observation(observation_id="obs_1", success=True, payload=None),
        _reflection(
            [
                {
                    "category": MemoryCategory.PREFERENCE.value,
                    "content": "用户偏好：称呼用户为老板",
                    "confidence": 1.0,
                    "source": "model",
                    "dedupe_key": "preference:call_boss",
                }
            ]
        ),
    )

    active = memory.query(MemoryLayer.SEMANTIC)
    assert len(active) == 1
    assert active[0].category is MemoryCategory.PREFERENCE


@pytest.mark.asyncio
async def test_address_preference_variants_converge(tmp_path) -> None:
    """「叫他X」与「希望被称呼为X」是同一偏好，应跨写入路径收敛。"""
    memory = AssistantMemory(tmp_path / "asst")

    memory.upsert(
        MemoryRecord(
            record_id="mem_add_3",
            content="用户称呼偏好：叫他「老板」",
            memory_type=MemoryLayer.SEMANTIC,
            importance=0.9,
            category=MemoryCategory.PREFERENCE,
            dedupe_key="user_address_preference",
            confidence=1.0,
            metadata={"source": "user"},
        )
    )
    await memory.update(
        _state(),
        Observation(observation_id="obs_1", success=True, payload=None),
        _reflection(
            [
                {
                    "category": MemoryCategory.PREFERENCE.value,
                    "content": "用户偏好：希望被称呼为老板",
                    "confidence": 1.0,
                    "source": "model",
                    "dedupe_key": "preference:call_boss",
                }
            ]
        ),
    )

    active = memory.query(MemoryLayer.SEMANTIC)
    assert len(active) == 1
