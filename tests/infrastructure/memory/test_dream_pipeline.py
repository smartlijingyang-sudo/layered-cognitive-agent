"""Dream slow path: trail consumption, intimacy ordering, alignment synthesis."""

from __future__ import annotations

import re
from pathlib import Path

from lca.contracts.atoms.enums.enums import MemoryCategory
from lca.contracts.models.memory.episode import EpisodeFact, ResidualClass
from lca.infrastructure.cli.commands.ops.memory import _dream_callbacks
from lca.infrastructure.memory.dream import run_dream
from lca.infrastructure.memory.episode_buffer import EpisodeBuffer

_MESSAGE = re.compile(r"message:([A-Za-z0-9_-]+)")


def _seed_home(tmp_path: Path) -> Path:
    home = tmp_path / "asst"
    (home / "memory" / "people").mkdir(parents=True)
    (home / "memory" / "groups").mkdir(parents=True)
    (home / "memory" / "episodes").mkdir(parents=True)
    (home / "memory" / "people" / "李雷.md").write_text("# 李雷\n\n常驻杭州\n", encoding="utf-8")
    (home / "memory" / "people" / "王安.md").write_text("# 王安\n\n产品负责人\n", encoding="utf-8")
    (home / "memory" / "groups" / "设计组.md").write_text(
        "# 设计组\n\n每周三同步\n", encoding="utf-8"
    )
    (home / "memory" / "2026-09-30.md").write_text(
        "# 2026-09-30\n\n- 李雷说项目下周发布\n- 用户偏好短回复\n",
        encoding="utf-8",
    )
    buffer = EpisodeBuffer(home)
    buffer.append(
        EpisodeFact(
            fact_id="ep-1",
            dedupe_key="pref:short_reply",
            category=MemoryCategory.PREFERENCE,
            content="用户偏好短回复",
            residual=ResidualClass.instruction,
            explicit_user_authority=True,
            source_trace_id="trace-1",
            observed_at_ms=1_759_200_000_000,
        )
    )
    buffer.append(
        EpisodeFact(
            fact_id="ep-2",
            dedupe_key="pref:short_reply",
            category=MemoryCategory.PREFERENCE,
            content="用户偏好短回复",
            residual=ResidualClass.instruction,
            explicit_user_authority=True,
            source_trace_id="trace-2",
            observed_at_ms=1_759_200_001_000,
        )
    )
    return home


def _assert_synthesis(home: Path) -> None:
    synthesis = home / "dreams" / "alignment" / "derived" / "ALIGNMENT_SYNTHESIS.md"
    assert synthesis.is_file()
    text = synthesis.read_text(encoding="utf-8")
    assertions = [line for line in text.splitlines() if line.startswith("- ")]
    assert assertions, "synthesis must contain assertions"
    for line in assertions:
        assert _MESSAGE.search(line), line


def test_dream_consumes_trail_and_produces_all_outputs(tmp_path: Path) -> None:
    home = _seed_home(tmp_path)
    now_ms = 1_759_200_000_000
    render, backfill = _dream_callbacks(home)
    report = run_dream(home, now_ms=now_ms, backfill=backfill, render=render)

    assert report.upserted >= 1
    assert report.trail_facts == 2
    assert report.people_indexed == 2
    assert report.groups_indexed == 1
    assert report.synthesis_written is True
    assert report.synthesis_path == "dreams/alignment/derived/ALIGNMENT_SYNTHESIS.md"

    memory_md = (home / "MEMORY.md").read_text(encoding="utf-8")
    assert "用户偏好短回复" in memory_md
    assert "李雷说项目下周发布" not in memory_md

    people_index = (home / "memory" / "people" / "INDEX.md").read_text(encoding="utf-8")
    groups_index = (home / "memory" / "groups" / "INDEX.md").read_text(encoding="utf-8")
    assert "李雷" in people_index
    assert "王安" in people_index
    assert "设计组" in groups_index

    _assert_synthesis(home)


def test_dream_second_run_is_idempotent(tmp_path: Path) -> None:
    home = _seed_home(tmp_path)
    now_ms = 1_759_200_000_000
    render, backfill = _dream_callbacks(home)
    first = run_dream(home, now_ms=now_ms, backfill=backfill, render=render)
    second = run_dream(home, now_ms=now_ms, backfill=backfill, render=render)
    assert first.upserted >= 1
    assert second.upserted == 0
    assert second.synthesis_written is True
    _assert_synthesis(home)


def test_a_render_without_a_backfill_leaves_user_md_alone(tmp_path: Path) -> None:
    """The half pair ``DreamCallbacks`` legally allows must neither write nor claim.

    ``_sync_user_md`` compares the rendering against disk first, so a home with
    identity or preference records and no ``USER.md`` always reaches the second
    half of that guard. Without ``backfill is None`` in it, the pass emits a
    preimage for a write that never happens and then raises on the ``None`` call.

    Reachable rather than theoretical. ``DreamCallbacks`` types the pair as
    ``tuple[_Render | None, _Backfill | None]``, and ``DreamFn``'s docstring
    already records a transposed pair that type-checked clean and degraded at
    runtime into a contained per-home failure. Nothing else drove it: the
    scheduler tests fake the pass, the plugin shape test replaces the scheduler,
    and the end-to-end scenario uses ``make_dream_callbacks``, which returns
    both callbacks or neither.
    """
    home = _seed_home(tmp_path)
    now_ms = 1_759_200_000_000
    render, _ = _dream_callbacks(home)

    report = run_dream(home, now_ms=now_ms, backfill=None, render=render)

    assert report.upserted >= 1, "promotion does not depend on the profile callbacks"
    assert report.user_md_written is False
    assert report.preimage is None
    assert not (home / "USER.md").exists()
    assert not (home / "revisions").exists(), "no preimage for a write that never happened"


def test_people_index_orders_by_intimacy(tmp_path: Path) -> None:
    home = _seed_home(tmp_path)
    now_ms = 1_759_200_000_000
    render, backfill = _dream_callbacks(home)
    run_dream(home, now_ms=now_ms, backfill=backfill, render=render)
    # 李雷 appears once in the trail corpus; 王安 appears zero times.
    people_page = (home / "memory" / "people" / "李雷.md").read_text(encoding="utf-8")
    assert "<!-- intimacy: 1" in people_page
    wang_page = (home / "memory" / "people" / "王安.md").read_text(encoding="utf-8")
    assert "intimacy" not in wang_page
