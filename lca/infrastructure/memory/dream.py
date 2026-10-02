"""Promote consolidated episode clusters into semantic memory (ADR-0249).

The caller supplies profile render and backfill. This module does not import
plugins or cognition, so a manifest digest cannot be revised from here.

ADR-0254 slow path: the dream pass also consumes the daily trail flow, keeps
people/groups INDEX.md ordered by intimacy, and writes
``dreams/alignment/derived/ALIGNMENT_SYNTHESIS.md`` whose assertions carry
``message:xxx`` evidence references.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from lca.contracts.atoms.enums.enums import MemoryCategory, MemoryLayer
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.mechanisms.content.addressable import sha256_hex
from lca.contracts.models.core.conversation.memory import MemoryRecord
from lca.contracts.models.memory.episode import (
    ClusterView,
    EpisodeFact,
    LifecycleState,
    ResidualClass,
    canonical_dedupe_key,
    consolidate,
)
from lca.infrastructure.memory.assistant_memory import AssistantMemory
from lca.infrastructure.memory.contextfiles.adapters.disk import DiskFileStore
from lca.infrastructure.memory.contextfiles.domain.alignment import (
    assertions_from_evidence,
)
from lca.infrastructure.memory.contextfiles.domain.layout import layout_for_home
from lca.infrastructure.memory.contextfiles.domain.trail import (
    TrailEntry,
    is_preference_statement,
    parse_trail,
)
from lca.infrastructure.memory.contextfiles.service.alignment import write_alignment_synthesis
from lca.infrastructure.memory.contextfiles.service.groups import GroupsDirectory
from lca.infrastructure.memory.contextfiles.service.indexing import build_memory_index
from lca.infrastructure.memory.contextfiles.service.people import PeopleDirectory
from lca.infrastructure.memory.episode_buffer import EpisodeBuffer
from lca.infrastructure.memory.fingerprint import content_fingerprint

_Backfill = Callable[[str, list[MemoryRecord]], object]
_Render = Callable[[Sequence[MemoryRecord]], str]

_SYNTHESIS_NOTE = (
    "这份综述由离线做梦管线从对话流水确定性生成。它是行为与沟通偏好的软调参，不是不可违抗的硬指令。"
)


class DreamReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    promoted: tuple[str, ...]
    upserted: int
    preimage: str | None
    user_md_written: bool
    trail_facts: int = 0
    people_indexed: int = 0
    groups_indexed: int = 0
    synthesis_written: bool = False
    synthesis_path: str = ""
    synthesis_assertions: int = 0
    index_documents: int = 0


def _already_active(memory: AssistantMemory, cluster: ClusterView) -> bool:
    target = content_fingerprint(cluster.content)
    for record in memory.query(MemoryLayer.SEMANTIC):
        key = canonical_dedupe_key(record.dedupe_key, record.category.value)
        if key == cluster.dedupe_key and record.content == cluster.content:
            return True
        if record.category == cluster.category and content_fingerprint(record.content) == target:
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


def _trail_facts(home: Path, *, now_ms: int) -> tuple[EpisodeFact, ...]:
    """Parse daily trail files into episode facts the consolidator understands."""

    layout = layout_for_home(home)
    store = DiskFileStore(home)
    facts: list[EpisodeFact] = []
    for name in store.list_dir(layout.trail_dir):
        if not name.endswith(".md"):
            continue
        relative = f"{layout.trail_dir}/{name}"
        try:
            text = store.read_text(relative)
        except OSError:
            continue
        source = name[: -len(".md")]
        for entry in parse_trail(text, source=source, observed_at_ms=now_ms):
            facts.append(_trail_episode(entry))
    return tuple(facts)


def _trail_episode(entry: TrailEntry) -> EpisodeFact:
    digest = sha256_hex(entry.content.encode("utf-8"), length=12)
    if is_preference_statement(entry.content):
        category = MemoryCategory.PREFERENCE
        authority = True
        raw_key = f"preference:{digest}"
    else:
        category = MemoryCategory.FACT
        authority = False
        raw_key = f"trail:{digest}"
    dedupe_key = canonical_dedupe_key(raw_key, category.value) or raw_key
    return EpisodeFact(
        fact_id=f"trail-{digest}",
        dedupe_key=dedupe_key,
        category=category,
        content=entry.content,
        residual=ResidualClass.instruction,
        explicit_user_authority=authority,
        source_trace_id=f"{entry.source}:{digest}",
        observed_at_ms=entry.observed_at_ms,
    )


def _refresh_relationships(home: Path, facts: Sequence[EpisodeFact]) -> tuple[int, int]:
    """Count mentions in the evidence and reorder people/groups indexes.

    Intimacy is the number of times a page's name or slug appears across the
    trail and episode evidence. The index then lists higher-intimacy pages
    first. Returns ``(people_indexed, groups_indexed)``.
    """

    layout = layout_for_home(home)
    store = DiskFileStore(home)
    corpus = "\n".join([fact.content for fact in facts])
    people = PeopleDirectory(store, layout=layout)
    groups = GroupsDirectory(store, layout=layout)
    people_indexed = 0
    for page in people.list():
        score = _mention_count(corpus, page)
        if people.set_intimacy(page.slug, score) is not None:
            people_indexed += 1
    groups_indexed = 0
    for page in groups.list():
        score = _mention_count(corpus, page)
        if groups.set_intimacy(page.slug, score) is not None:
            groups_indexed += 1
    return people_indexed, groups_indexed


def _mention_count(corpus: str, page: object) -> float:
    name = str(getattr(page, "name", "") or "").strip()
    slug = str(getattr(page, "slug", "") or "").strip()
    needles = {needle for needle in (name, slug) if needle}
    return float(sum(corpus.count(needle) for needle in needles))


def _write_synthesis(
    home: Path, facts: Sequence[EpisodeFact], *, now_ms: int
) -> tuple[bool, str, int]:
    """Write ALIGNMENT_SYNTHESIS.md from the evidence and return its stats."""

    layout = layout_for_home(home)
    evidence: list[tuple[str, str]] = [
        (fact.fact_id, fact.content)
        for fact in facts
        if fact.content.strip()
        and fact.category in {MemoryCategory.PREFERENCE, MemoryCategory.IDENTITY}
    ]
    assertions = list(assertions_from_evidence(evidence))
    date = datetime.fromtimestamp(now_ms / 1000, tz=UTC).strftime("%Y-%m-%d")
    path = write_alignment_synthesis(
        DiskFileStore(home),
        assertions,
        date=date,
        note=_SYNTHESIS_NOTE,
        layout=layout,
    )
    return True, path, len(assertions)


def run_dream(
    home: Path,
    *,
    now_ms: int,
    backfill: _Backfill | None,
    render: _Render | None = None,
) -> DreamReport:
    """Consolidate the episode and trail flow once and upsert new semantic rows.

    The pass also refreshes relationship indexes and writes the nightly
    alignment synthesis.
    """

    home = Path(home)
    loaded = EpisodeBuffer(home).read_all()
    trail_facts = _trail_facts(home, now_ms=now_ms)
    facts = loaded.facts + trail_facts
    plan = consolidate(facts, now_ms=now_ms)
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
    people_indexed, groups_indexed = _refresh_relationships(home, facts)
    synthesis_written, synthesis_path, synthesis_assertions = _write_synthesis(
        home, facts, now_ms=now_ms
    )
    index_documents = build_memory_index(
        home,
        DiskFileStore(home),
        memory.query(MemoryLayer.SEMANTIC),
    )
    return DreamReport(
        promoted=tuple(promoted),
        upserted=upserted,
        preimage=preimage,
        user_md_written=user_md_written,
        trail_facts=len(trail_facts),
        people_indexed=people_indexed,
        groups_indexed=groups_indexed,
        synthesis_written=synthesis_written,
        synthesis_path=synthesis_path,
        synthesis_assertions=synthesis_assertions,
        index_documents=index_documents,
    )


__all__ = ["DreamReport", "run_dream"]
