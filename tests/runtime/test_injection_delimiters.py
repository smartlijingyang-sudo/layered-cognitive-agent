"""INV-INJECTION-DELIMITER-INTEGRITY — injected blocks are strictly delimited."""

from __future__ import annotations

from lca.infrastructure.memory.contextfiles.domain.standing import (
    refresh_injected,
    render_injected,
)


def test_render_injected_wraps_strictly() -> None:
    block = render_injected("MEMORY.md", "用户住在杭州")
    assert block.startswith("<!-- INJECTED FILE: MEMORY.md -->\n")
    assert block.endswith("\n<!-- END INJECTED FILE: MEMORY.md -->")
    assert block.count("<!-- INJECTED FILE:") == 1
    assert block.count("<!-- END INJECTED FILE:") == 1


def test_refresh_injected_keeps_blocks_balanced() -> None:
    text = "规则\n" + render_injected("MEMORY.md", "旧记忆") + "\n"
    out = refresh_injected(text, [("MEMORY.md", "新记忆")])
    assert out.count("<!-- INJECTED FILE: MEMORY.md -->") == 1
    assert out.count("<!-- END INJECTED FILE: MEMORY.md -->") == 1
    assert "新记忆" in out
    assert "旧记忆" not in out


def test_refresh_injected_appends_missing_standing_files() -> None:
    text = "规则\n" + render_injected("SOUL.md", "人设")
    out = refresh_injected(
        text,
        [("SOUL.md", "人设"), ("USER.md", "用户画像")],
        order=("SOUL.md", "USER.md"),
    )
    for name in ("SOUL.md", "USER.md"):
        assert f"<!-- INJECTED FILE: {name} -->" in out
        assert f"<!-- END INJECTED FILE: {name} -->" in out
    assert out.count("<!-- INJECTED FILE:") == 2
    assert out.count("<!-- END INJECTED FILE:") == 2


def test_marker_less_history_stays_unchanged() -> None:
    text = "没有注入块的历史提示\n"
    out = refresh_injected(text, [("MEMORY.md", "新记忆")])
    assert out == text
