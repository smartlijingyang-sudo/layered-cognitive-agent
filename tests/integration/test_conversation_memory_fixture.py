"""PR-2（ADR-0246）：连续对话记忆回归夹具测试。

给定 4 轮用户消息序列，断言第二轮检索结果能引用第一轮产生的记忆，
且无原文整句噪音（结构化 content）。
"""

from __future__ import annotations

from lca.contracts.atoms.enums.enums import MemoryCategory
from tests.support.memory_harness import (
    FakeMemoryExtractor,
    InMemoryMemoryStore,
    MemoryCandidate,
    run_conversation_turns,
)

FOUR_TURN_SCRIPT = [
    "我是架构师",
    "你记得我是谁吗",
    "我不喜欢啰嗦",
    "还是简洁一点好",
]


def test_second_turn_can_reference_first_turn_identity() -> None:
    store = InMemoryMemoryStore()
    extractor = FakeMemoryExtractor(
        candidates=[
            MemoryCandidate(
                category=MemoryCategory.IDENTITY,
                content="用户身份：架构师",
                dedupe_key="identity:architect",
            )
        ]
    )

    retrieved_per_turn = run_conversation_turns(store, extractor, FOUR_TURN_SCRIPT)

    # 第二轮检索应包含第一轮产生的身份记忆
    turn_2 = retrieved_per_turn[1]
    assert any("架构师" in r.content for r in turn_2)


def test_memory_content_is_structured_not_raw_quote() -> None:
    store = InMemoryMemoryStore()
    extractor = FakeMemoryExtractor(
        candidates=[
            MemoryCandidate(
                category=MemoryCategory.PREFERENCE,
                content="用户偏好：不喜欢啰嗦",
                dedupe_key="preference:concise",
            )
        ]
    )

    run_conversation_turns(store, extractor, FOUR_TURN_SCRIPT)

    records = store.query(category=MemoryCategory.PREFERENCE)
    assert len(records) == 1
    # 结构化事实而非原文整句
    assert records[0].content == "用户偏好：不喜欢啰嗦"
    assert "我不喜欢啰嗦" not in records[0].content


def test_extractor_fast_path_no_candidates_produces_empty_memory() -> None:
    store = InMemoryMemoryStore()
    extractor = FakeMemoryExtractor(candidates=[])

    retrieved_per_turn = run_conversation_turns(store, extractor, FOUR_TURN_SCRIPT)

    assert store.query() == []
    assert all(len(turn) == 0 for turn in retrieved_per_turn)
