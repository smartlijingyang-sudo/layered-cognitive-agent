"""Scenario: 48-hour continuous memory evolution through the shipped dream path.

Simulates two consecutive days of trail and episode evidence, running the
real ``run_dream`` pipeline each day. Asserts consolidated MEMORY.md, intimacy
re-ranking, and synthesis regeneration with fresh message references.
"""

from __future__ import annotations

from pathlib import Path

from lca.contracts.atoms.enums.enums import MemoryCategory
from lca.contracts.models.memory.episode import EpisodeFact, ResidualClass
from lca.infrastructure.cli.commands.ops.memory import _dream_callbacks
from lca.infrastructure.memory.dream import run_dream
from lca.infrastructure.memory.episode_buffer import EpisodeBuffer


def _seed_day1(home: Path) -> None:
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


def test_two_day_flow_consolidates_and_reranks(tmp_path: Path) -> None:
    home = tmp_path / "asst"
    _seed_day1(home)
    now = 1_759_200_000_000
    render, backfill = _dream_callbacks(home)
    day1 = run_dream(home, now_ms=now, backfill=backfill, render=render)
    assert day1.upserted >= 1
    assert "用户偏好短回复" in (home / "MEMORY.md").read_text(encoding="utf-8")
    assert "李雷说项目下周发布" not in (home / "MEMORY.md").read_text(encoding="utf-8")
    li_page = (home / "memory" / "people" / "李雷.md").read_text(encoding="utf-8")
    assert "intimacy: 1" in li_page

    # Day 2: 李雷 mentioned again, 王安 mentioned once. 李雷 stays on top.
    (home / "memory" / "2026-10-01.md").write_text(
        "# 2026-10-01\n\n- 李雷确认发布窗口\n- 王安评审通过\n- 李雷补充测试计划\n",
        encoding="utf-8",
    )
    day2 = run_dream(home, now_ms=now + 86_400_000, backfill=backfill, render=render)
    assert day2.upserted == 0
    assert day2.trail_facts == 5
    people_index = (home / "memory" / "people" / "INDEX.md").read_text(encoding="utf-8")
    assert people_index.index("李雷") < people_index.index("王安")
    li_page2 = (home / "memory" / "people" / "李雷.md").read_text(encoding="utf-8")
    assert "intimacy: 3" in li_page2
    synthesis = (home / "dreams" / "alignment" / "derived" / "ALIGNMENT_SYNTHESIS.md").read_text(
        encoding="utf-8"
    )
    assert "用户偏好短回复" in synthesis
    assert "李雷说项目下周发布" not in synthesis
    assert "message:" in synthesis
