"""契约测试：四层认知记忆领域模型与不可变契约（对齐 ADR-0277 SSOT）。"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from lca.cognition.memory.types import (
    EpisodicTrace,
    SemanticClaim,
    WorkingMemoryPercept,
)
from lca.contracts.protocols.memory.cognitive import (
    EntityGraphPort,
    InternalRecallPort,
    WorkingMemoryPort,
)


def test_working_memory_percept_contract() -> None:
    wm = WorkingMemoryPercept(
        task_goal="查询亲戚结婚礼数",
        focal_entities=("xiaowen", "cousin"),
        active_cues=("wedding", "gift"),
        observed_at_ms=1727932800000,
    )
    assert wm.task_goal == "查询亲戚结婚礼数"
    assert "xiaowen" in wm.focal_entities
    assert "wedding" in wm.active_cues
    assert wm.observed_at_ms == 1727932800000

    # 不可变性验证
    with pytest.raises(FrozenInstanceError):
        wm.task_goal = "篡改任务"  # type: ignore[misc]

    # 非空校验
    with pytest.raises(ValueError, match="task_goal 不允许为空"):
        WorkingMemoryPercept(task_goal="   ")


def test_semantic_claim_compatible_extension() -> None:
    now = datetime.now(UTC)
    claim = SemanticClaim(
        id="claim_01",
        claim="全栈使用 Rust 与 Go",
        confidence=1.0,
        sources=("trace_01",),
        valid_from=now,
        category="preference",
        dedupe_key="preference:tech_stack",
        sensitivity="normal",
    )
    assert claim.id == "claim_01"
    assert claim.category == "preference"
    assert claim.dedupe_key == "preference:tech_stack"
    assert claim.sensitivity == "normal"
    assert claim.is_valid_at(now)

    # 不可变性验证
    with pytest.raises(FrozenInstanceError):
        claim.claim = "修改"  # type: ignore[misc]


def test_episodic_trace_compatible_extension() -> None:
    now = datetime.now(UTC)
    trace = EpisodicTrace(
        id="trace_01",
        when=now,
        ingested_at=now,
        who=("user", "assistant"),
        what="执行 ssh 登录 252 机器失败",
        salience=0.9,
        associated_tool="ssh",
        ttl_days=30,
    )
    assert trace.associated_tool == "ssh"
    assert trace.ttl_days == 30
    assert trace.salience == 0.9

    with pytest.raises(FrozenInstanceError):
        trace.what = "修改"  # type: ignore[misc]


def test_cognitive_memory_ports_protocol() -> None:
    class DummyWorkingMemory:
        def get_active_percept(self) -> WorkingMemoryPercept | None:
            return None

        def update_percept(self, percept: WorkingMemoryPercept) -> None:
            pass

    class DummyEntityGraph:
        def write_entity(
            self,
            domain: str,
            slug: str,
            content: str,
            tags: tuple[str, ...] = (),
            aliases: tuple[str, ...] = (),
        ) -> None:
            pass

        def read_entity(self, domain: str, slug: str) -> str | None:
            return None

        def search_entities(self, query: str, limit: int = 10) -> list[str]:
            return []

        def get_active_graph_index(self) -> str:
            return ""

    class DummyRecall:
        def recall(self, query: str, max_hops: int = 2) -> dict[str, object]:
            return {"query": query, "has_recalled": False}

    assert isinstance(DummyWorkingMemory(), WorkingMemoryPort)
    assert isinstance(DummyEntityGraph(), EntityGraphPort)
    assert isinstance(DummyRecall(), InternalRecallPort)
