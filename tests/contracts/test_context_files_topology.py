"""INV-TOPOLOGY-ALLOWLIST — home root entries stay inside the allowlist."""

from __future__ import annotations

from pathlib import Path

from lca.infrastructure.memory.contextfiles.domain.layout import (
    allowed_root_entries,
    packaged_layout,
    validate_root_entries,
)


def test_allowed_root_entries_cover_the_landed_files() -> None:
    allowed = allowed_root_entries()
    for name in ("SOUL.md", "IDENTITY.md", "USER.md", "MEMORY.md", "AGENTS.md", "TOOLS.md"):
        assert name in allowed
    for root in ("memory", "side-chats", "dreams", "revisions", "skills", "workspace"):
        assert root in allowed


def test_home_with_only_allowed_entries_passes(tmp_path: Path) -> None:
    home = tmp_path / "asst"
    home.mkdir()
    for name in ("SOUL.md", "USER.md", "MEMORY.md", "AGENTS.md", "TOOLS.md"):
        (home / name).write_text(f"body-{name}\n", encoding="utf-8")
    for directory in ("memory", "side-chats", "dreams", "revisions", "skills", "workspace"):
        (home / directory).mkdir(exist_ok=True)
    entries = tuple(entry.name for entry in sorted(home.iterdir()))
    assert validate_root_entries(entries) == ()


def test_disallowed_root_entry_is_reported(tmp_path: Path) -> None:
    home = tmp_path / "asst"
    home.mkdir()
    (home / "SOUL.md").write_text("soul\n", encoding="utf-8")
    (home / "tmp-upload").mkdir()
    entries = tuple(entry.name for entry in sorted(home.iterdir()))
    violations = validate_root_entries(entries)
    assert violations == ("tmp-upload",)


def test_layout_standing_files_are_non_empty() -> None:
    layout = packaged_layout()
    assert all(name for name in layout.standing_files)
    assert len(set(layout.standing_files)) == len(layout.standing_files)
