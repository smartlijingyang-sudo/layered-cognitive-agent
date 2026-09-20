"""PR-10（ADR-0246）：4 轮连续对话跨 run 记忆端到端回归。

每轮是一个独立 run（共享同一 assistant 记忆库），验证：
- 第 1 轮身份陈述 → identity 落盘
- 第 2 轮隐式引用 → 检索上下文携带 identity（agent 可引用）
- 第 3 轮偏好陈述 → preference 落盘
- 第 4 轮冲突纠正 → 旧偏好被 supersede，无重复堆积

使用 harness 的 fake extractor（不调用真实 LLM，CI 可直接运行）。
"""

from __future__ import annotations

from lca.contracts.atoms.enums.enums import MemoryCategory, MemoryLayer
from lca.contracts.models.core.conversation.memory import MemoryRecord
from tests.support.memory_harness import FixedRetrievalPolicy, InMemoryMemoryStore


class _ScriptedExtractor:
    """按用户文本返回对应候选的脚本化 fake extract。"""

    def __init__(self, script: list[tuple[str, list[dict[str, object]]]]) -> None:
        self._script = script
        self.calls: list[str] = []

    def extract(self, user_text: str) -> list[dict[str, object]]:
        self.calls.append(user_text)
        for text, candidates in self._script:
            if text == user_text:
                return list(candidates)
        return []


_ROUNDS = [
    ("我是架构师", "identity"),
    ("你记得我是谁吗", "identity"),
    ("我不喜欢啰嗦", "preference"),
    ("还是简洁一点好", "preference"),
]


def _candidate(category: str, content: str, dedupe_key: str) -> dict[str, object]:
    return {
        "category": category,
        "content": content,
        "confidence": 1.0,
        "source": "user",
        "dedupe_key": dedupe_key,
    }


def _script() -> list[tuple[str, list[dict[str, object]]]]:
    return [
        ("我是架构师", [_candidate("identity", "用户身份：架构师", "identity:architect")]),
        ("你记得我是谁吗", []),
        ("我不喜欢啰嗦", [_candidate("preference", "用户偏好：不喜欢啰嗦", "preference:concise")]),
        (
            "还是简洁一点好",
            [_candidate("preference", "用户偏好：简洁回复", "preference:concise")],
        ),
    ]


def _run_round(
    store: InMemoryMemoryStore,
    extractor: _ScriptedExtractor,
    policy: FixedRetrievalPolicy,
    user_text: str,
) -> list[MemoryRecord]:
    candidates = extractor.extract(user_text)
    for cand in candidates:
        record = MemoryRecord(
            record_id=f"mem_{len(store.all()) + 1}",
            content=str(cand["content"]),
            memory_type=MemoryLayer.SEMANTIC,
            importance=0.9,
            category=MemoryCategory(str(cand["category"])),
            dedupe_key=cand.get("dedupe_key") if isinstance(cand.get("dedupe_key"), str) else None,
            confidence=1.0,
            created_at_ms=len(store.all()),
        )
        store.upsert(record)
    return policy.retrieve(store.query(include_superseded=True), query=user_text)


def test_cross_run_memory_four_rounds() -> None:
    store = InMemoryMemoryStore()
    extractor = _ScriptedExtractor(_script())
    policy = FixedRetrievalPolicy()
    retrieved_per_round: list[list[MemoryRecord]] = []

    for user_text, _kind in _ROUNDS:
        retrieved = _run_round(store, extractor, policy, user_text)
        retrieved_per_round.append(retrieved)

    # 第 2 轮检索上下文携带第 1 轮身份（agent 可引用「架构师」）
    round_2 = retrieved_per_round[1]
    assert any("架构师" in r.content for r in round_2)

    # 第 4 轮纠正后，旧偏好被 supersede，只保留新偏好
    active_preferences = store.query(category=MemoryCategory.PREFERENCE)
    assert len(active_preferences) == 1
    assert active_preferences[0].content == "用户偏好：简洁回复"

    # 无重复堆积：身份 + 偏好各一条活跃
    active_identity = store.query(category=MemoryCategory.IDENTITY)
    assert len(active_identity) == 1
    assert len(store.query()) == 2

    # 第 4 轮检索上下文携带纠正后的偏好
    round_4 = retrieved_per_round[3]
    assert any("简洁回复" in r.content for r in round_4)
