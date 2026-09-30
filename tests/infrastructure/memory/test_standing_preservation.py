"""Standing blocks survive reuse of an older prompt."""

from __future__ import annotations

from pathlib import Path

from lca.infrastructure.memory.contextfiles.adapters.disk import DiskFileStore
from lca.infrastructure.memory.contextfiles.domain.standing import (
    STANDING_LIVE_NOTE,
    refresh_injected,
    render_injected,
)
from lca.infrastructure.memory.contextfiles.events.publisher import (
    InProcessEventPublisher,
    StandingPreserved,
)
from lca.infrastructure.memory.contextfiles.service.compaction import (
    preserve_standing_sections,
)


def test_refresh_injected_replaces_body_and_keeps_surrounding_text() -> None:
    old = "\n".join(
        [
            "系统规则保持不动",
            render_injected("MEMORY.md", "用户住在上海"),
            "后面的工具说明",
        ]
    )
    out = refresh_injected(old, [("MEMORY.md", "用户住在杭州")])
    assert "系统规则保持不动" in out
    assert "后面的工具说明" in out
    assert "用户住在杭州" in out
    assert "用户住在上海" not in out
    assert STANDING_LIVE_NOTE in out


def test_refresh_injected_does_not_truncate_a_long_file() -> None:
    body = "记" * 5000
    out = refresh_injected(render_injected("MEMORY.md", "短"), [("MEMORY.md", body)])
    assert body in out


def test_refresh_injected_leaves_marker_less_text_unchanged() -> None:
    assert refresh_injected("from-fold", [("MEMORY.md", "新事实")]) == "from-fold"


def test_refresh_injected_is_idempotent() -> None:
    once = refresh_injected(render_injected("SOUL.md", "人设"), [("SOUL.md", "人设")])
    twice = refresh_injected(once, [("SOUL.md", "人设")])
    assert once == twice
    assert once.count(STANDING_LIVE_NOTE) == 1


def test_refresh_injected_drops_a_blank_file() -> None:
    out = refresh_injected(render_injected("TOOLS.md", "旧工具"), [("TOOLS.md", "  ")])
    assert "旧工具" not in out
    assert "<!-- INJECTED FILE: TOOLS.md -->" not in out


def test_preserve_standing_sections_reads_disk_and_publishes(tmp_path: Path) -> None:
    (tmp_path / "MEMORY.md").write_text("用户住在杭州\n", encoding="utf-8")
    publisher = InProcessEventPublisher()
    events: list[object] = []
    publisher.subscribe(events.append)
    out = preserve_standing_sections(
        render_injected("MEMORY.md", "用户住在上海"),
        DiskFileStore(tmp_path),
        publisher,
    )
    assert "用户住在杭州" in out
    assert "用户住在上海" not in out
    assert len(events) == 1
    assert isinstance(events[0], StandingPreserved)
    assert "MEMORY.md" in events[0].names
    assert events[0].changed is True
