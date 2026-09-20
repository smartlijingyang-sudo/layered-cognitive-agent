"""PR-4（ADR-0246）：``SimpleMemorySystem.retrieve`` 注入不超过 token 预算。"""

from __future__ import annotations

import pytest

from lca.cognition.memory.layered.retrieval_policy import (
    LayeredRetrievalPolicy,
    estimate_tokens,
)
from lca.cognition.memory.policy.policy import MemoryAuthority, MemoryWrite
from lca.cognition.memory.simple.memory import SimpleMemorySystem
from lca.contracts.atoms.enums.enums import MemoryLayer, MemoryRecordKind
from lca.contracts.models.core.perceive.perception import ContextManifest


def _write(record_id: str, content: str) -> MemoryWrite:
    return MemoryWrite(
        record_id=record_id,
        layer=MemoryLayer.SEMANTIC,
        authority=MemoryAuthority.USER_CONFIRMED,
        content=content,
        confidence=1.0,
        kind=MemoryRecordKind.GENERIC,
        metadata={},
    )


@pytest.mark.asyncio
async def test_retrieve_respects_token_budget() -> None:
    system = SimpleMemorySystem(retrieval=LayeredRetrievalPolicy())
    system.commit(
        (
            _write("mem_1", "用户身份：架构师，" + "详细背景" * 20),
            _write("mem_2", "用户偏好：不喜欢啰嗦，" + "补充说明" * 20),
            _write("mem_3", "一般事实：" + "长文本" * 30),
        )
    )

    manifest = ContextManifest(items=())
    records = await system.retrieve(manifest, query="架构师", token_budget=30)

    used = sum(estimate_tokens(r.content) for r in records)
    assert used <= 30
    assert len(records) < 3


@pytest.mark.asyncio
async def test_retrieve_without_budget_returns_within_record_cap() -> None:
    system = SimpleMemorySystem(retrieval=LayeredRetrievalPolicy())
    system.commit(
        (
            _write("mem_1", "事实一"),
            _write("mem_2", "事实二"),
            _write("mem_3", "事实三"),
        )
    )

    manifest = ContextManifest(items=())
    records = await system.retrieve(manifest, query="")
    assert len(records) >= 1
