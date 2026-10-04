"""Standing blocks survive reuse of an older prompt."""

from __future__ import annotations

from pathlib import Path

from lca.infrastructure.memory.contextfiles.adapters.disk import DiskFileStore
from lca.infrastructure.memory.contextfiles.domain.layout import packaged_layout
from lca.infrastructure.memory.contextfiles.domain.standing import (
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
    assert packaged_layout().live_note in out


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
    assert once.count(packaged_layout().live_note) == 1


def test_refresh_injected_drops_a_blank_file() -> None:
    out = refresh_injected(render_injected("TOOLS.md", "旧工具"), [("TOOLS.md", "  ")])
    assert "旧工具" not in out
    assert "<!-- INJECTED FILE: TOOLS.md -->" not in out


def test_refresh_injected_collapses_a_repeated_file_to_one_block() -> None:
    """Two copies of one file in the incoming prompt converge to one.

    ``run_16bb13cc3385`` carried 91930 chars of system prompt with 22 BEGIN
    markers, 23 END markers, and three SOUL.md blocks. ``seen`` used to gate
    only the append-missing tail, so the walk refreshed every occurrence it
    found and the duplication survived every turn.
    """
    doubled = "\n\n".join(
        [
            render_injected("SOUL.md", "旧人设"),
            render_injected("MEMORY.md", "旧事实"),
            render_injected("SOUL.md", "旧人设"),
            render_injected("MEMORY.md", "旧事实"),
        ]
    )
    out = refresh_injected(doubled, [("SOUL.md", "新人设"), ("MEMORY.md", "新事实")])

    assert out.count("<!-- INJECTED FILE: SOUL.md -->") == 1
    assert out.count("<!-- INJECTED FILE: MEMORY.md -->") == 1
    assert out.count("新人设") == 1
    assert out.count("新事实") == 1
    assert "旧人设" not in out
    assert refresh_injected(out, [("SOUL.md", "新人设"), ("MEMORY.md", "新事实")]) == out


def test_refresh_injected_closes_a_block_on_its_own_end_marker() -> None:
    """A nested block does not close its parent and leak the rest as prose.

    ``BackstorySection`` wraps an already-marked-up bundle in SOUL.md markers,
    so the incoming text nests. Matching any END marker let the inner block
    terminate the outer one early, and everything after it was copied through
    verbatim, which is how one bundle became two.
    """
    inner = "\n\n".join(
        [render_injected("SOUL.md", "内层人设"), render_injected("USER.md", "内层用户")]
    )
    nested = f"<!-- INJECTED FILE: SOUL.md -->\n{inner}\n<!-- END INJECTED FILE: SOUL.md -->"
    out = refresh_injected(nested, [("SOUL.md", "外层人设"), ("USER.md", "外层用户")])

    assert out.count("<!-- INJECTED FILE: SOUL.md -->") == 1
    assert out.count("<!-- INJECTED FILE: USER.md -->") == 1
    assert out.count("<!-- END INJECTED FILE: SOUL.md -->") == 1
    assert "内层人设" not in out
    assert "内层用户" not in out
    assert "外层人设" in out
    assert "外层用户" in out


def test_refresh_injected_drops_an_unmatched_end_marker() -> None:
    """A stray END marker is dropped rather than copied into the prompt."""
    text = render_injected("SOUL.md", "人设") + "\n<!-- END INJECTED FILE: SOUL.md -->"
    out = refresh_injected(text, [("SOUL.md", "人设")])

    assert out.count("<!-- INJECTED FILE: SOUL.md -->") == 1
    assert out.count("<!-- END INJECTED FILE: SOUL.md -->") == 1


def test_preserve_standing_sections_reads_disk_and_publishes(tmp_path: Path) -> None:
    (tmp_path / "MEMORY.md").write_text("用户住在杭州\n", encoding="utf-8")
    publisher = InProcessEventPublisher()
    events: list[object] = []
    publisher.subscribe(events.append)
    out = preserve_standing_sections(
        render_injected("MEMORY.md", "用户住在上海"),
        DiskFileStore(tmp_path),
        publisher,
        platform_root=tmp_path / "shared",
    )
    assert "用户住在杭州" in out
    assert "用户住在上海" not in out
    assert len(events) == 1
    assert isinstance(events[0], StandingPreserved)
    assert "MEMORY.md" in events[0].names
    assert events[0].changed is True
