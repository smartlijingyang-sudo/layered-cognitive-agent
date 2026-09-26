"""Promote consolidated episode clusters into semantic memory (ADR-0249).

The caller supplies profile render and backfill. This module does not import
plugins or cognition, so a manifest digest cannot be revised from here.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from lca.contracts.atoms.enums.enums import MemoryCategory, MemoryLayer
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.conversation.memory import MemoryRecord
from lca.contracts.models.memory.episode import (
    ClusterView,
    LifecycleState,
    canonical_dedupe_key,
    consolidate,
)
from lca.infrastructure.memory.assistant_memory import AssistantMemory
from lca.infrastructure.memory.episode_buffer import EpisodeBuffer

_Backfill = Callable[[str, list[MemoryRecord]], object]
_Render = Callable[[Sequence[MemoryRecord]], str]


class DreamReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    promoted: tuple[str, ...]
    upserted: int
    preimage: str | None
    user_md_written: bool


def _already_active(memory: AssistantMemory, cluster: ClusterView) -> bool:
    for record in memory.query(MemoryLayer.SEMANTIC):
        key = canonical_dedupe_key(record.dedupe_key, record.category.value)
        if key == cluster.dedupe_key and record.content == cluster.content:
            return True
    return False


def _identity_preference(memory: AssistantMemory) -> list[MemoryRecord]:
    return [
        record
        for record in memory.query(MemoryLayer.SEMANTIC)
        if record.category in {MemoryCategory.IDENTITY, MemoryCategory.PREFERENCE}
    ]


def _sync_user_md(
    home: Path,
    memory: AssistantMemory,
    *,
    now_ms: int,
    render: _Render | None,
    backfill: _Backfill | None,
) -> tuple[str | None, bool]:
    if render is None:
        return None, False
    records = _identity_preference(memory)
    desired = render(records).encode()
    user_md = home / "USER.md"
    current = user_md.read_bytes() if user_md.is_file() else b""
    if desired == current or backfill is None:
        return None, False
    revisions = home / "revisions"
    revisions.mkdir(parents=True, exist_ok=True)
    preimage = revisions / f"user-md-preimage-{now_ms}.md"
    preimage.write_bytes(current)
    backfill(home.name, records)
    return str(preimage), True


def run_dream(
    home: Path,
    *,
    now_ms: int,
    backfill: _Backfill | None,
    render: _Render | None = None,
) -> DreamReport:
    """Consolidate the episode buffer once and upsert only new semantic rows."""
    home = Path(home)
    loaded = EpisodeBuffer(home).read_all()
    plan = consolidate(loaded.facts, now_ms=now_ms)
    memory = AssistantMemory(home)
    promoted: list[str] = []
    upserted = 0
    for cluster in plan.clusters:
        if cluster.lifecycle is not LifecycleState.consolidated_slow:
            continue
        promoted.append(cluster.dedupe_key)
        if _already_active(memory, cluster):
            continue
        memory.upsert(
            MemoryRecord(
                record_id=new_id("mem"),
                content=cluster.content,
                memory_type=MemoryLayer.SEMANTIC,
                importance=0.9,
                category=cluster.category,
                dedupe_key=cluster.dedupe_key,
                source_trace_id=cluster.source_trace_id,
                confidence=0.9,
                metadata={"source": "dream", "episode_recurrence": cluster.recurrence},
            )
        )
        upserted += 1
    preimage, user_md_written = _sync_user_md(
        home,
        memory,
        now_ms=now_ms,
        render=render,
        backfill=backfill,
    )
    return DreamReport(
        promoted=tuple(promoted),
        upserted=upserted,
        preimage=preimage,
        user_md_written=user_md_written,
    )


__all__ = ["DreamReport", "run_dream"]
