"""``refresh_standing_backstory`` reads the five standing files from disk."""

from __future__ import annotations

from pathlib import Path

from lca.infrastructure.memory.contextfiles.service.assembly import refresh_standing_backstory


def test_refresh_reads_standing_files_in_budget_order(tmp_path: Path) -> None:
    home = tmp_path / "asst"
    home.mkdir()
    (home / "SOUL.md").write_text("人设正文", encoding="utf-8")
    (home / "USER.md").write_text("称呼小超", encoding="utf-8")
    (home / "MEMORY.md").write_text("用户住在杭州", encoding="utf-8")
    (home / "AGENTS.md").write_text("手册内容", encoding="utf-8")

    refreshed = refresh_standing_backstory(str(home), fallback="old")
    assert "人设正文" in refreshed
    assert "称呼小超" in refreshed
    assert "用户住在杭州" in refreshed
    assert "手册内容" in refreshed


def test_refresh_returns_latest_disk_content(tmp_path: Path) -> None:
    home = tmp_path / "asst"
    home.mkdir()
    (home / "MEMORY.md").write_text("旧事实", encoding="utf-8")
    assert "旧事实" in refresh_standing_backstory(str(home), fallback="old")

    (home / "MEMORY.md").write_text("新事实", encoding="utf-8")
    refreshed = refresh_standing_backstory(str(home), fallback="old")
    assert "新事实" in refreshed
    assert "旧事实" not in refreshed


def test_refresh_missing_home_returns_fallback(tmp_path: Path) -> None:
    assert refresh_standing_backstory(str(tmp_path / "nope"), fallback="old") == "old"


def test_refresh_empty_home_returns_fallback(tmp_path: Path) -> None:
    home = tmp_path / "asst"
    home.mkdir()
    assert refresh_standing_backstory(str(home), fallback="old") == "old"
