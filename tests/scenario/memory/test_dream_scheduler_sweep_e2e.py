"""End-to-end pin on the Phase 0 dream sweep (ADR-0287 §4).

Every collaborator here is the production one: the real ``run_dream``, the real
``make_dream_callbacks`` factory, the real ``write_dream_evidence``. The
kernel-restart leg this task's brief proposed is cancelled by ruling R60. The
plugin ships behind ``enabled: false`` until the ADR-0254 v3 ownership conflict
recorded in R54 is resolved, and a disabled plugin's ``setup()`` returns before
constructing anything, so a restart would prove only that the bundle entry
resolves. ``scripts/check_plan_lift.py`` and the shape test's ``resolve_profile``
prove that instead.

No test here reaches a real assistant home. ``run_dream`` rewrites
``MEMORY.md``, ``USER.md``, the people and groups indexes and the FTS index,
and ``_sync_user_md`` emits a preimage under ``{home}/revisions/``, so every
home is built under ``tmp_path``. What contains that is home-relative
resolution all the way through ``run_dream``. The shared ``isolated_lca_home``
fixture each test requests is belt and braces, because nothing on this path
reads ``LCA_HOME``: only the plugin's ``setup()`` does, to resolve the host
lock directory, and these tests build the scheduler directly.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from lca.application.memory.dream_scheduler import (
    DreamScheduler,
    make_dream_callbacks,
    write_dream_evidence,
)
from lca.contracts.atoms.enums.enums import MemoryCategory
from lca.contracts.models.assistant.spec import AssistantSpec
from lca.contracts.models.memory.episode import EpisodeFact, ResidualClass
from lca.contracts.protocols.assistant.catalog import (
    AssistantHandle,
    AssistantSummary,
    CreateAssistantRequest,
    PlanRevision,
    ProfilePatch,
)
from lca.infrastructure.memory.episode_buffer import EpisodeBuffer

CONTENT = "用户身份：架构师"
USER_MD = "# 用户画像\n\n## 身份\n- 用户身份：架构师\n"
FIRST_TICK_MS = 1_791_121_000_000
TICK_MS = 300_000


class _PersistingCatalog:
    """``AssistantCatalog`` stand-in that persists the one field the sweep writes.

    ``_AssistantCatalogImpl.revise_profile`` writes ``patch.user_md`` to
    ``{home}/USER.md`` (``lca/plugins/domain/assistant/catalog/handlers.py``).
    A double that only recorded the call would leave the file on disk unchanged,
    so ``_sync_user_md`` would see a rendering that still differs on every later
    tick and report ``user_md_written=True`` forever. The evidence-stability
    assertion below would then fail on the double rather than on the sweep.

    Every protocol member is present, not just the one that does work. The
    alternative was suppressing the argument type at the
    ``make_dream_callbacks`` call, and a suppression standing in for a missing
    surface is how a real signature change slips past. It is also what the
    plugin's own guard asks for: ``isinstance(catalog, AssistantCatalog)`` on a
    runtime-checkable protocol answers by member presence.
    """

    def __init__(self, homes: Mapping[str, Path]) -> None:
        self._homes = dict(homes)
        self.revised: list[tuple[str, ProfilePatch]] = []

    def create(self, req: CreateAssistantRequest) -> AssistantHandle:
        raise NotImplementedError

    def get(self, assistant_id: str) -> AssistantSpec:
        raise NotImplementedError

    def list(self, user_id: str | None = None) -> tuple[AssistantSummary, ...]:
        del user_id
        return ()

    def revise_profile(
        self, assistant_id: str, patch: ProfilePatch, *, actor: str = "system"
    ) -> PlanRevision:
        del actor
        self.revised.append((assistant_id, patch))
        if patch.user_md is not None:
            (self._homes[assistant_id] / "USER.md").write_text(patch.user_md, encoding="utf-8")
        return PlanRevision(
            assistant_id=assistant_id,
            revision_seq=len(self.revised),
            manifest_digest="0" * 64,
            actor="system",
            snapshot_path=f"revisions/{len(self.revised)}.json",
        )

    def reimport(self, assistant_id: str, reason: str) -> PlanRevision:
        raise NotImplementedError

    def retire(self, assistant_id: str, reason: str) -> None:
        raise NotImplementedError


def _identity_fact(trace_id: str) -> EpisodeFact:
    """An episode the daytime capture path would have appended.

    ``explicit_user_authority`` plus an IDENTITY category is what takes the
    first-occurrence branch of ``_lifecycle``, so one fact from one trace
    consolidates instead of waiting for a recurrence that the governed capture
    path never produces.
    """
    return EpisodeFact(
        fact_id=f"ep_{trace_id}",
        dedupe_key="identity:role",
        category=MemoryCategory.IDENTITY,
        content=CONTENT,
        residual=ResidualClass.instruction,
        explicit_user_authority=True,
        source_trace_id=trace_id,
        observed_at_ms=FIRST_TICK_MS,
    )


def _production_sweep(
    tmp_path: Path, home: Path, catalog: _PersistingCatalog, clock: list[int]
) -> DreamScheduler:
    """The sweep the plugin builds, minus the plugin's own boot wiring.

    ``run_dream_fn`` is deliberately not passed: its default is the real
    consolidation pass, which is the subject here.
    """
    return DreamScheduler(
        # Discovery is a bare literal because the fleet-shaped cost it hides is
        # the reason it runs off the event loop: listing the catalog reads and
        # parses every home's manifest.json, measured at 3905ms cold and 130ms
        # warm for 576 summaries, on the loop the kernel serves HTTP from (R51).
        homes=lambda: [home],
        lock_dir=tmp_path / "locks",
        tick_seconds=300,
        now_ms=lambda: clock[0],
        evidence_writer=write_dream_evidence,
        callbacks=make_dream_callbacks(catalog),
    )


def _semantic_rows(home: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = json.loads(
        (home / "memory" / "semantic.json").read_text(encoding="utf-8")
    )
    return rows


def _evidence(home: Path) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(
        (home / "dreams" / "last_run.json").read_text(encoding="utf-8")
    )
    return payload


def _seeded_home(tmp_path: Path) -> tuple[Path, _PersistingCatalog, list[int], DreamScheduler]:
    home = (tmp_path / "asst_test").resolve()
    catalog = _PersistingCatalog({"asst_test": home})
    EpisodeBuffer(home).append(_identity_fact("trace_a"))
    clock = [FIRST_TICK_MS]
    return home, catalog, clock, _production_sweep(tmp_path, home, catalog, clock)


async def test_a_sweep_promotes_a_captured_episode_and_leaves_evidence(
    tmp_path: Path, isolated_lca_home: Path
) -> None:
    del isolated_lca_home
    home, catalog, _, scheduler = _seeded_home(tmp_path)

    (report,) = await scheduler.sweep_once()

    assert report is not None, "the home is unlocked and catalogued, so nothing skips it"
    assert report.upserted == 1
    assert report.user_md_written is True, (
        "True only when make_dream_callbacks supplied both render and backfill; "
        "_locked_pass passes (None, None) without a factory, so this is the proof "
        "the callbacks wire is live and not merely present"
    )

    rows = _semantic_rows(home)
    assert [row["content"] for row in rows if not row["deleted"]] == [CONTENT]
    assert len(rows) == 1, "one fact promotes to one row, with nothing retired beside it"
    assert rows[0]["metadata"]["source"] == "dream"
    assert rows[0]["dedupe_key"] == "identity:role"

    assert _evidence(home) == {
        "now_ms": FIRST_TICK_MS,
        "upserted": 1,
        "user_md_written": True,
        "trail_facts": 0,
        "index_documents": 1,
    }, "R40's payload: promoted and synthesis_written are not readable at face value"

    assert (home / "USER.md").read_text(encoding="utf-8") == USER_MD
    # _sync_user_md writes only when the rendering differs from what is on disk,
    # so the first enabled tick over a real fleet is a bounded one-time
    # convergence: one USER.md rewrite plus one preimage per changed home. A
    # read-only scan found 8 of 578 production homes in that state, which is why
    # R54 keeps the plugin disabled until ADR-0254 v3 settles who owns USER.md.
    preimages = sorted((home / "revisions").glob("user-md-preimage-*.md"))
    assert [preimage.name for preimage in preimages] == [f"user-md-preimage-{FIRST_TICK_MS}.md"], (
        "the preimage is named by the tick that took it, not by wall clock"
    )
    assert preimages[0].read_text(encoding="utf-8") == "", "the home had no USER.md before"
    assert [assistant_id for assistant_id, _ in catalog.revised] == ["asst_test"], (
        "_sync_user_md addresses the catalog by home.name, so the backfill lands "
        "on the assistant the sweep is dreaming"
    )


async def test_a_second_sweep_promotes_nothing_and_keeps_the_evidence_stable(
    tmp_path: Path, isolated_lca_home: Path
) -> None:
    del isolated_lca_home
    home, catalog, clock, scheduler = _seeded_home(tmp_path)
    await scheduler.sweep_once()
    artifact = home / "dreams" / "last_run.json"
    stamp = artifact.stat().st_mtime_ns
    before = _semantic_rows(home)
    user_md_stamp = (home / "USER.md").stat().st_mtime_ns

    clock[0] += TICK_MS
    (second,) = await scheduler.sweep_once()

    assert second is not None
    assert second.upserted == 0, (
        "the regression lock on the 17-of-89 duplicate-dimension defect: "
        "_already_active recognises the row the first sweep wrote, so a fact "
        "already in semantic memory is not promoted a second time"
    )
    assert second.promoted == ("identity:role",), (
        "run_dream appends to promoted before the _already_active skip, so the "
        "cluster keeps being re-decided forever. This is why R40 dropped promoted "
        "from the payload: it counts re-decisions, not changes"
    )
    assert second.user_md_written is False, "USER.md already holds the rendering"

    after = _semantic_rows(home)
    assert len(after) == len(before), "a repeated sweep must not add a second row for one fact"
    assert [row["record_id"] for row in after] == [row["record_id"] for row in before], (
        "the surviving row is the first sweep's, not a superseding rewrite of it"
    )
    assert artifact.stat().st_mtime_ns == stamp
    assert _evidence(home)["now_ms"] == FIRST_TICK_MS, (
        "the payload is the proof the file was left alone, not only its mtime"
    )
    assert (home / "USER.md").stat().st_mtime_ns == user_md_stamp
    assert len(catalog.revised) == 1, "the convergence is one-time, not one per tick"
    assert len(list((home / "revisions").glob("user-md-preimage-*.md"))) == 1


async def test_a_tick_that_only_reprojects_the_profile_still_updates_the_evidence(
    tmp_path: Path, isolated_lca_home: Path
) -> None:
    """A pass that moves no fact but re-renders USER.md is a change.

    This is the R54 convergence shape on a home that has already dreamed once,
    and the reason ``user_md_written`` is half of ``_changed`` rather than a
    passenger in the payload. Drop it from the predicate and a home whose
    profile the sweep repaired reports the previous promotion forever.
    """
    del isolated_lca_home
    home, catalog, clock, scheduler = _seeded_home(tmp_path)
    await scheduler.sweep_once()
    stale_profile = "# 用户画像\n"
    (home / "USER.md").write_text(stale_profile, encoding="utf-8")

    clock[0] += TICK_MS
    (third,) = await scheduler.sweep_once()

    assert third is not None
    assert third.upserted == 0, "the episode is already active, so nothing promotes"
    assert third.user_md_written is True

    assert _evidence(home) == {
        "now_ms": FIRST_TICK_MS + TICK_MS,
        "upserted": 0,
        "user_md_written": True,
        "trail_facts": 0,
        "index_documents": 1,
    }, "the artifact follows the pass that re-projected the profile, not the last promotion"
    assert (home / "USER.md").read_text(encoding="utf-8") == USER_MD

    preimages = sorted((home / "revisions").glob("user-md-preimage-*.md"))
    assert [preimage.name for preimage in preimages] == [
        f"user-md-preimage-{FIRST_TICK_MS}.md",
        f"user-md-preimage-{FIRST_TICK_MS + TICK_MS}.md",
    ]
    assert preimages[1].read_text(encoding="utf-8") == stale_profile, (
        "the bytes the sweep replaced are recoverable, which is what makes a "
        "fleet-wide first tick reversible"
    )
    assert len(catalog.revised) == 2
