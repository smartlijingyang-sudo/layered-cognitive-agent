"""Memory test harness（ADR-0246 PR-2）。

提供内存版 ``MemoryStore``、确定性检索策略与可注入的 fake 提取器，使记忆
相关测试不依赖真实 LLM 与文件系统。生产代码不得 import 本模块。
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from lca.contracts.atoms.enums.enums import MemoryCategory, MemoryLayer
from lca.contracts.models.core.conversation.memory import MemoryRecord
from lca.contracts.protocols.memory.memory import MemoryStore

__all__ = [
    "FakeMemoryExtractor",
    "FixedRetrievalPolicy",
    "InMemoryMemoryStore",
    "MemoryCandidate",
    "run_conversation_turns",
]


@dataclass(frozen=True, slots=True)
class MemoryCandidate:
    """LLM 蒸馏输出的结构化候选（ADR-0246 §3.2 extract 产物）。

    ``category`` / ``content`` 必填；``dedupe_key`` 用于 admit 去重与
    supersede 血缘。
    """

    category: MemoryCategory
    content: str
    confidence: float = 0.9
    source: str = "user"
    dedupe_key: str | None = None


class InMemoryMemoryStore(MemoryStore):
    """内存版 ``MemoryStore``：``upsert`` 按 ``dedupe_key`` 幂等。

    ``supersede`` 把旧记录标记 ``deleted=True`` 并设置 ``retired_at_ms``，
    新记录通过 ``revision_of`` 指向旧记录。``query`` 默认排除已退役记录。
    """

    def __init__(self) -> None:
        self._records: dict[str, MemoryRecord] = {}

    def upsert(self, record: MemoryRecord) -> MemoryRecord:
        existing = self._by_dedupe_key(record.dedupe_key) if record.dedupe_key else None
        if existing is not None and existing.record_id != record.record_id:
            self.supersede(existing.record_id, record, reason="dedupe_key replacement")
            return self._records[record.record_id]
        self._records[record.record_id] = record
        return record

    def supersede(
        self,
        record_id: str,
        replacement: MemoryRecord,
        *,
        reason: str = "superseded",
    ) -> MemoryRecord:
        old = self._records.get(record_id)
        if old is not None:
            self._records[record_id] = replace(
                old,
                deleted=True,
                retired_at_ms=replacement.created_at_ms or 0,
                metadata={**old.metadata, "superseded_reason": reason},
            )
        updated = replace(replacement, revision_of=record_id)
        self._records[updated.record_id] = updated
        return updated

    def query(
        self,
        *,
        category: MemoryCategory | None = None,
        include_superseded: bool = False,
        limit: int = 50,
    ) -> list[MemoryRecord]:
        records = [
            r
            for r in self._records.values()
            if (include_superseded or not r.deleted)
            and (category is None or r.category is category)
        ]
        records.sort(key=lambda r: r.created_at_ms or 0, reverse=True)
        return records[:limit]

    def all(self) -> list[MemoryRecord]:
        return list(self._records.values())

    def _by_dedupe_key(self, key: str) -> MemoryRecord | None:
        for r in self._records.values():
            if r.dedupe_key == key and not r.deleted:
                return r
        return None


class FixedRetrievalPolicy:
    """确定性检索策略：identity/preference 优先，其次 importance 降序。

    按字符级 token 估算截断到 ``budget``，排除已退役记录。结果确定，
    同一输入两次调用返回一致（PR-4 排序确定性）。
    """

    def __init__(self, budget: int = 2000) -> None:
        self._budget = budget

    def retrieve(
        self,
        records: list[MemoryRecord],
        *,
        query: str = "",
        budget: int | None = None,
    ) -> list[MemoryRecord]:
        del query
        limit = budget if budget is not None else self._budget
        active = [r for r in records if not r.deleted]
        active.sort(
            key=lambda r: (
                r.category in {MemoryCategory.IDENTITY, MemoryCategory.PREFERENCE},
                r.importance,
            ),
            reverse=True,
        )
        kept: list[MemoryRecord] = []
        used = 0
        for r in active:
            estimated = max(1, len(r.content) // 4)
            if used + estimated > limit:
                break
            kept.append(r)
            used += estimated
        return kept


class FakeMemoryExtractor:
    """可注入的 fake ``extract``：返回固定候选，记录每次调用文本。"""

    def __init__(self, candidates: list[MemoryCandidate] | None = None) -> None:
        self._candidates = list(candidates or [])
        self.calls: list[str] = []

    def extract(self, user_text: str) -> list[MemoryCandidate]:
        self.calls.append(user_text)
        return list(self._candidates)


def run_conversation_turns(
    store: InMemoryMemoryStore,
    extractor: FakeMemoryExtractor,
    user_texts: list[str],
    *,
    policy: FixedRetrievalPolicy | None = None,
) -> list[list[MemoryRecord]]:
    """跑一个连续对话回归：每轮 extract → upsert → 检索。

    返回每轮检索到的活跃记录列表（供断言「第二轮能引用第一轮记忆」）。
    """
    policy = policy or FixedRetrievalPolicy()
    per_turn_retrieved: list[list[MemoryRecord]] = []
    for text in user_texts:
        candidates = extractor.extract(text)
        for cand in candidates:
            record = MemoryRecord(
                record_id=f"mem_{len(store.all()) + 1}",
                content=cand.content,
                memory_type=MemoryLayer.SEMANTIC,
                importance=0.9 if cand.confidence >= 0.8 else 0.5,
                category=cand.category,
                dedupe_key=cand.dedupe_key,
                confidence=cand.confidence,
                created_at_ms=len(store.all()),
            )
            store.upsert(record)
        retrieved = policy.retrieve(store.query(include_superseded=True))
        per_turn_retrieved.append(retrieved)
    return per_turn_retrieved
