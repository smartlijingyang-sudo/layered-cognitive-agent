"""INV-COMPACTION-STANDING-PRESERVATION — compaction never dilutes standing files."""

from __future__ import annotations

from pathlib import Path

from lca.infrastructure.memory.contextfiles.adapters.disk import DiskFileStore
from lca.infrastructure.memory.contextfiles.domain.standing import (
    rehydrate_after_compaction,
    render_injected,
)
from lca.infrastructure.memory.contextfiles.service.compaction import preserve_standing_sections


def test_rehydrate_reinjects_the_exact_disk_bytes(tmp_path: Path) -> None:
    disk_content = "用户住在杭州\n"
    (tmp_path / "MEMORY.md").write_text(disk_content, encoding="utf-8")
    history = "历史对话摘要……\n" + render_injected("MEMORY.md", "用户住在上海\n")
    compacted = rehydrate_after_compaction(
        history,
        files=[("MEMORY.md", disk_content)],
        budget_chars=2000,
    )
    assert render_injected("MEMORY.md", disk_content) in compacted
    assert "用户住在上海" not in compacted


def test_preserve_standing_replaces_blocks_from_disk(tmp_path: Path) -> None:
    disk_content = "新内容\n"
    (tmp_path / "MEMORY.md").write_text(disk_content, encoding="utf-8")
    folded = "历史规则\n" + render_injected("MEMORY.md", "旧内容\n")
    out = preserve_standing_sections(folded, DiskFileStore(tmp_path))
    assert render_injected("MEMORY.md", disk_content) in out
    assert "旧内容" not in out


def test_compaction_budget_splits_standing_and_history(tmp_path: Path) -> None:
    disk_content = "用户住在杭州\n"
    (tmp_path / "MEMORY.md").write_text(disk_content, encoding="utf-8")
    history = "历史对话摘要……\n" + render_injected("MEMORY.md", "旧内容\n")
    compacted = rehydrate_after_compaction(
        history,
        files=[("MEMORY.md", disk_content)],
        budget_chars=200,
    )
    assert len(compacted) <= 200
    assert "用户住在杭州" in compacted
