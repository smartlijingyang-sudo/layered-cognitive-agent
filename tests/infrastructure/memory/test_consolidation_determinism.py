"""ADR-0249: consolidate is a pure fold over distinct traces."""

from __future__ import annotations

from lca.contracts.atoms.enums.enums import MemoryCategory
from lca.contracts.models.memory.episode import (
    EpisodeFact,
    LifecycleState,
    ResidualClass,
    consolidate,
)

_NOW = 1_700_000_000_000


def _fact(
    fact_id: str,
    trace_id: str,
    content: str,
    observed_at_ms: int,
    *,
    category: MemoryCategory = MemoryCategory.PREFERENCE,
    dedupe_key: str = "preference:verbosity",
    explicit: bool = False,
) -> EpisodeFact:
    return EpisodeFact(
        fact_id=fact_id,
        dedupe_key=dedupe_key,
        category=category,
        content=content,
        residual=ResidualClass.instruction,
        explicit_user_authority=explicit,
        source_trace_id=trace_id,
        observed_at_ms=observed_at_ms,
    )


def test_consolidate_twice_is_the_same_value() -> None:
    episodes = (
        _fact("ep_a", "t1", "用户偏好：简洁", _NOW),
        _fact("ep_b", "t1", "用户偏好：简洁", _NOW),
        _fact("ep_c", "t2", "用户偏好：详细", _NOW + 5),
    )
    plan = consolidate(episodes, now_ms=_NOW)
    assert plan == consolidate(episodes, now_ms=_NOW)
    assert plan == consolidate(tuple(reversed(episodes)), now_ms=_NOW)
    slow = [
        cluster
        for cluster in plan.clusters
        if cluster.lifecycle is LifecycleState.consolidated_slow
    ]
    assert len(slow) == 1
    assert slow[0].content == "用户偏好：详细"
    assert slow[0].recurrence == 2


def test_explicit_identity_promotes_at_recurrence_one() -> None:
    episodes = (
        _fact(
            "ep_role",
            "t1",
            "用户身份：架构师",
            _NOW,
            category=MemoryCategory.IDENTITY,
            dedupe_key="identity:role",
            explicit=True,
        ),
    )
    plan = consolidate(episodes, now_ms=_NOW)
    assert len(plan.clusters) == 1
    cluster = plan.clusters[0]
    assert cluster.content == "用户身份：架构师"
    assert cluster.recurrence == 1
    assert cluster.lifecycle is LifecycleState.consolidated_slow
