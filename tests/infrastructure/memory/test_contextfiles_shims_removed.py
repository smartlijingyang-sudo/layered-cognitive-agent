"""Tests verifying residual contextfiles forwarding shims are removed (INV-ARCH-12).

The three forwarding shims (``domain/diff.py``, ``domain/edit.py`` and
``service/memory_edit_sync.py``) must be physically deleted, and no non-doc
import may reference the old paths.
"""

from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).parents[3]

_SHIM_PATHS = (
    "lca/infrastructure/memory/contextfiles/domain/diff.py",
    "lca/infrastructure/memory/contextfiles/domain/edit.py",
    "lca/infrastructure/memory/contextfiles/service/memory_edit_sync.py",
)

_OLD_MODULES = (
    "contextfiles.domain.diff",
    "contextfiles.domain.edit",
    "contextfiles.service.memory_edit_sync",
)

_SKIPPED_DIRS = {
    ".git",
    ".venv",
    "vendor",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}


def _iter_source_files() -> list[tuple[Path, str]]:
    """Yield (repo-relative path, text) for every non-vendored Python file."""
    files: list[tuple[Path, str]] = []
    for py_file in _REPO_ROOT.rglob("*.py"):
        rel = py_file.relative_to(_REPO_ROOT)
        if any(part in _SKIPPED_DIRS for part in rel.parts):
            continue
        files.append((rel, py_file.read_text(encoding="utf-8-sig")))
    return files


def test_inv_arch_12_shim_files_physically_deleted() -> None:
    """INV-ARCH-12: The three forwarding shims no longer exist on disk."""
    for rel in _SHIM_PATHS:
        assert not (_REPO_ROOT / rel).exists(), f"Residual forwarding shim still present: {rel}"


def test_inv_arch_12_no_old_path_imports_remain() -> None:
    """INV-ARCH-12: No repo Python file imports a shim path."""
    hits: list[str] = []
    for rel, text in _iter_source_files():
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in _OLD_MODULES or any(
                        alias.name.startswith(f"{module}.") for module in _OLD_MODULES
                    ):
                        hits.append(f"{rel}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod in _OLD_MODULES or any(
                    mod.startswith(f"{module}.") for module in _OLD_MODULES
                ):
                    hits.append(f"{rel}: from {mod} import ...")
    assert hits == [], f"Found old-path imports: {hits}"
