"""Test unified contextfiles sync module and boundary invariants (INV-ARCH-06).

Consolidates diff.py, edit.py, and memory_edit_sync.py into sync.py without
referencing ports.file_store, verifying diffing, staleness guards, and claim reconciliation.
"""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lca.contracts.atoms.enums.enums import MemoryCategory, MemoryLayer
from lca.contracts.models.core.conversation.memory import MemoryRecord
from lca.infrastructure.memory.contextfiles.sync import (
    FileVersion,
    MemoryEditSyncService,
    StaleSnapshotOperationError,
    parse_memory_markdown_claims,
    render_standing_diff,
    require_fresh,
    sync_memory_markdown,
    unified_diff,
)


def test_inv_arch_06_sync_has_no_file_store_import() -> None:
    """INV-ARCH-06: sync.py must not reference ports.file_store."""
    sync_path = (
        Path(__file__).parents[3]
        / "lca"
        / "infrastructure"
        / "memory"
        / "contextfiles"
        / "sync.py"
    )
    assert sync_path.is_file(), f"Expected {sync_path} to exist"

    tree = ast.parse(sync_path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "file_store" not in alias.name
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            assert "file_store" not in mod


def test_unified_diff_and_render() -> None:
    """Verify diff generation and multi-file rendering in sync.py."""
    before = "line 1\nline 2\n"
    after = "line 1\nline 2 modified\n"

    diff = unified_diff("MEMORY.md", before, after)
    assert "--- MEMORY.md" in diff
    assert "+++ MEMORY.md" in diff
    assert "-line 2" in diff
    assert "+line 2 modified" in diff

    # Identical texts produce empty diff
    assert unified_diff("MEMORY.md", before, before) == ""

    # Multi-file diff render
    rendered = render_standing_diff([("MEMORY.md", diff), ("USER.md", "")])
    assert "常驻文件有更新" in rendered
    assert "+line 2 modified" in rendered


def test_require_fresh_staleness_guard() -> None:
    """Verify read-before-write staleness check in sync.py."""
    v1 = FileVersion(path="MEMORY.md", mtime_ns=1000)
    v1_same = FileVersion(path="MEMORY.md", mtime_ns=1000)
    v2 = FileVersion(path="MEMORY.md", mtime_ns=2000)

    # Identical versions pass
    require_fresh(v1, v1_same)
    require_fresh(None, None)

    # Changed mtime raises
    with pytest.raises(StaleSnapshotOperationError, match="file changed during edit"):
        require_fresh(v1, v2)

    # Disappeared / appeared raise
    with pytest.raises(StaleSnapshotOperationError, match="file disappeared"):
        require_fresh(v1, None)

    with pytest.raises(StaleSnapshotOperationError, match="file appeared"):
        require_fresh(None, v1)


def test_parse_memory_markdown_claims() -> None:
    """Verify markdown claim parsing with sections and embedded IDs."""
    md = """
# Header ignored

## Preferences
- User prefers Python <!-- id:mem_pref_1 -->
- User likes concise diffs

## Facts
- LCA is written in Python <!-- id:mem_fact_1 -->
- 暂无事实记录
"""
    parsed = parse_memory_markdown_claims(md)
    assert len(parsed) == 3

    assert parsed[0] == (MemoryCategory.PREFERENCE, "User prefers Python", "mem_pref_1")
    assert parsed[1] == (MemoryCategory.PREFERENCE, "User likes concise diffs", None)
    assert parsed[2] == (MemoryCategory.FACT, "LCA is written in Python", "mem_fact_1")


def test_sync_memory_markdown_reconciles_claims() -> None:
    """Verify MemoryEditSyncService applies ADD, SUPERSEDE, and DELETE operations."""
    memory = MagicMock()

    existing_pref = MemoryRecord(
        record_id="mem_pref_1",
        content="User prefers Python",
        category=MemoryCategory.PREFERENCE,
        memory_type=MemoryLayer.SEMANTIC,
        importance=0.9,
    )
    existing_to_delete = MemoryRecord(
        record_id="mem_fact_old",
        content="Old fact to be deleted",
        category=MemoryCategory.FACT,
        memory_type=MemoryLayer.SEMANTIC,
        importance=0.5,
    )

    memory.query.return_value = [existing_pref, existing_to_delete]

    # Markdown updates existing_pref, omits existing_to_delete, and adds new_fact
    new_md = """
## Preferences
- User prefers Python and Rust <!-- id:mem_pref_1 -->

## Facts
- Antigravity is pair programming assistant
"""
    service = MemoryEditSyncService(memory)
    counts = service.apply_markdown_edit(new_md)

    assert counts == {"added": 1, "superseded": 1, "deleted": 1}

    # Verify supersede was called for mem_pref_1
    memory.supersede.assert_called_once()
    assert memory.supersede.call_args[0][0] == "mem_pref_1"
    assert memory.supersede.call_args[0][1].content == "User prefers Python and Rust"

    # Verify upsert was called for new fact
    memory.upsert.assert_called_once()
    assert memory.upsert.call_args[0][0].content == "Antigravity is pair programming assistant"

    # Verify remove was called for omitted record
    memory.remove.assert_called_once_with("mem_fact_old")

    # Verify projection refreshed
    memory._project_curated.assert_called_once_with(())

    # Test convenience function wrapper
    memory.reset_mock()
    memory.query.return_value = []
    c2 = sync_memory_markdown(memory, "## Facts\n- Fact 1")
    assert c2["added"] == 1
    memory.upsert.assert_called_once()
