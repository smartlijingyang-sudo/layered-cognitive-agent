"""Frozen episode facts and the pure consolidation fold (ADR-0249).

Daytime residuals land here, not on ``MemoryRecord``. Lifecycle is computed
on the plan; episode files do not store a counter.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from lca.contracts.atoms.enums.enums import MemoryCategory


class ResidualClass(StrEnum):
    error = "error"
    correction = "correction"
    instruction = "instruction"


class LifecycleState(StrEnum):
    ephemeral_fast = "ephemeral_fast"
    consolidated_slow = "consolidated_slow"


class EpisodeFact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    fact_id: str
    dedupe_key: str = Field(min_length=1)
    category: MemoryCategory
    content: str = Field(min_length=1)
    residual: ResidualClass
    explicit_user_authority: bool
    source_trace_id: str = Field(min_length=1)
    observed_at_ms: int = Field(ge=0)


class ClusterView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    dedupe_key: str
    lifecycle: LifecycleState
    content: str
    category: MemoryCategory
    recurrence: int
    source_trace_id: str
    supporting_trace_ids: tuple[str, ...]
    observed_at_ms: int = Field(ge=0)
    explicit_user_authority: bool
    loser_fact_ids: tuple[str, ...]


class ConsolidationPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    clusters: tuple[ClusterView, ...]


def canonical_dedupe_key(dedupe_key: str | None, category: str | None = None) -> str | None:
    """Normalize a dedupe key: strip, lower, hyphen to underscore, prefix category."""
    if not dedupe_key:
        return None
    key = str(dedupe_key).strip().lower().replace("-", "_")
    if ":" not in key and category:
        cat = str(category).strip().lower()
        if cat:
            key = f"{cat}:{key}"
    return key


def _lifecycle(winner: EpisodeFact, recurrence: int) -> LifecycleState:
    if winner.category == MemoryCategory.IDENTITY and winner.explicit_user_authority:
        return LifecycleState.consolidated_slow
    if recurrence >= 2:
        return LifecycleState.consolidated_slow
    return LifecycleState.ephemeral_fast


def _cluster(dedupe_key: str, group: Sequence[EpisodeFact]) -> ClusterView:
    winner = max(group, key=lambda fact: (fact.observed_at_ms, fact.fact_id))
    recurrence = len({fact.source_trace_id for fact in group})
    return ClusterView(
        dedupe_key=dedupe_key,
        lifecycle=_lifecycle(winner, recurrence),
        content=winner.content,
        category=winner.category,
        recurrence=recurrence,
        source_trace_id=winner.source_trace_id,
        supporting_trace_ids=tuple(sorted({fact.source_trace_id for fact in group})),
        observed_at_ms=winner.observed_at_ms,
        explicit_user_authority=winner.explicit_user_authority,
        loser_fact_ids=tuple(sorted(fact.fact_id for fact in group if fact is not winner)),
    )


def consolidate(episodes: Sequence[EpisodeFact], *, now_ms: int) -> ConsolidationPlan:
    """Fold episodes into a plan. ``now_ms`` is unused: every fact carries ``observed_at_ms``."""
    del now_ms
    groups: dict[str, list[EpisodeFact]] = {}
    for fact in episodes:
        key = canonical_dedupe_key(fact.dedupe_key, fact.category.value)
        if not key:
            continue
        groups.setdefault(key, []).append(fact)
    clusters = tuple(
        sorted(
            (_cluster(key, group) for key, group in groups.items()),
            key=lambda cluster: cluster.dedupe_key,
        )
    )
    return ConsolidationPlan(clusters=clusters)


__all__ = [
    "ClusterView",
    "ConsolidationPlan",
    "EpisodeFact",
    "LifecycleState",
    "ResidualClass",
    "canonical_dedupe_key",
    "consolidate",
]
