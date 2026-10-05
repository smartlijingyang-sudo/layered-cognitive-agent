"""Tests verifying removal of legacy contextfiles shims (INV-ARCH-12)."""

from __future__ import annotations

from pathlib import Path


def test_inv_arch_12_shim_files_deleted() -> None:
    """INV-ARCH-12: The 3 forwarding shims must not exist in the codebase."""
    root = Path(__file__).resolve().parents[3]
    shim_paths = [
        root / "lca/infrastructure/memory/contextfiles/domain/diff.py",
        root / "lca/infrastructure/memory/contextfiles/domain/edit.py",
        root / "lca/infrastructure/memory/contextfiles/service/memory_edit_sync.py",
    ]
    for p in shim_paths:
        assert not p.exists(), f"Stale forwarding shim still exists: {p}"


def test_inv_arch_12_no_imports_to_deleted_shims() -> None:
    """INV-ARCH-12: No python files in lca/ or tests/ import from deleted shims."""
    root = Path(__file__).resolve().parents[3]
    forbidden = (
        "contextfiles.domain.diff",
        "contextfiles.domain.edit",
        "contextfiles.service.memory_edit_sync",
    )
    violations: list[str] = []
    for base in (root / "lca", root / "tests"):
        for py_path in base.rglob("*.py"):
            text = py_path.read_text(encoding="utf-8", errors="ignore")
            for term in forbidden:
                if term in text and py_path != Path(__file__).resolve():
                    violations.append(f"{py_path.relative_to(root)}: {term}")

    assert violations == [], f"Found imports pointing to deleted shims: {violations}"


def test_inv_arch_12_all_symbols_available_from_sync() -> None:
    """INV-ARCH-12: All functionality is provided directly by contextfiles.sync."""
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

    assert issubclass(StaleSnapshotOperationError, RuntimeError)
    assert callable(render_standing_diff)
    assert callable(unified_diff)
    assert callable(require_fresh)
    assert callable(parse_memory_markdown_claims)
    assert callable(sync_memory_markdown)
    assert MemoryEditSyncService is not None
    assert FileVersion is not None
