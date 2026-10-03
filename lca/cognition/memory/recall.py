"""System 2 内部多跳追忆引擎与认知工具 (Cognitive Saccade & Deliberate Recall)。

结合 ADR-0277 评分与开放知识图谱，在思考（Think）阶段提供最多 2 跳的关系扩散追忆，
未命中时诚实返回 NoRecall 与不确定性标注，绝不编造事实。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from lca.infrastructure.memory.entities.store import EntityGraphStore


@dataclass(frozen=True)
class RecallResult:
    """内部追忆结果（不可变 DTO）。"""

    has_recalled: bool
    query: str
    recalled_claims: tuple[str, ...]
    relation_chains: tuple[tuple[tuple[str, str, str], ...], ...]
    hops_count: int
    uncertainty_note: str


class SystemTwoRecallEngine:
    """System 2 内部多跳追忆引擎。"""

    def __init__(self, store: EntityGraphStore) -> None:
        self.store = store

    def recall(
        self,
        query: str,
        start_slug: str | None = None,
        max_hops: int = 2,
    ) -> RecallResult:
        """执行认知追忆：结合 FTS 实体搜索与多跳关系路径遍历。"""
        # 深度保护：严格限制最大递归跳数为 2
        safe_hops = min(max(max_hops, 1), 2)

        # 1. 实体图谱全文检索
        hits = self.store.search_entities(query=query, limit=5)
        if not hits:
            return RecallResult(
                has_recalled=False,
                query=query,
                recalled_claims=(),
                relation_chains=(),
                hops_count=0,
                uncertainty_note="未检索到任何关联实体或事实记忆，请诚实承认记忆缺失，绝不编造事实。",
            )

        # 2. 关系链遍历（寻找从 start_slug 到各目标实体的扩散路径）
        chains: list[tuple[tuple[str, str, str], ...]] = []
        max_hop_reached = 1
        for hit in hits:
            if start_slug and hit.slug != start_slug:
                path = self.store.get_relation_path(
                    source_slug=start_slug, target_slug=hit.slug, max_hops=safe_hops
                )
                if path:
                    chains.append(tuple(path))
                    max_hop_reached = max(max_hop_reached, len(path))

        # 3. 收集关联实体事实陈述
        claims: list[str] = []
        for hit in hits:
            claims.append(f"[{hit.domain}/{hit.slug}] {hit.content}")

        return RecallResult(
            has_recalled=True,
            query=query,
            recalled_claims=tuple(claims),
            relation_chains=tuple(chains),
            hops_count=max_hop_reached,
            uncertainty_note="",
        )


class InternalRecallTool:
    """Agent 内部追忆认知工具。"""

    name: str = "internal_recall"
    description: str = "内部认知追忆：在思维（Think）阶段主动检索长期记忆、实体图谱与多跳关联关系。"

    def __init__(self, engine: SystemTwoRecallEngine) -> None:
        self.engine = engine

    def run(
        self,
        query: str,
        start_slug: str = "me",
        max_hops: int = 2,
    ) -> dict[str, Any]:
        """执行内部追忆并返回结构化字典供 Agent 决策。"""
        result = self.engine.recall(query=query, start_slug=start_slug, max_hops=max_hops)
        return {
            "has_recalled": result.has_recalled,
            "query": result.query,
            "recalled_claims": list(result.recalled_claims),
            "relation_chains": [
                [{"source": s, "target": t, "relation": r} for s, t, r in chain]
                for chain in result.relation_chains
            ],
            "hops_count": result.hops_count,
            "uncertainty_note": result.uncertainty_note,
        }
