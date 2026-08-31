"""Tests for scripts/migrate_layer_rename.py."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from migrate_layer_rename import (  # noqa: E402
    LAYER_TO_SEMANTIC,
    find_references,
    replace_imports,
    run_git_mv,
)


def test_layer_to_semantic_has_all_5_mappings():
    assert len(LAYER_TO_SEMANTIC) == 5
    assert "lca.infrastructure" in LAYER_TO_SEMANTIC
    assert "lca.cognition" in LAYER_TO_SEMANTIC
    assert "lca.runtime" in LAYER_TO_SEMANTIC
    assert "lca.agent" in LAYER_TO_SEMANTIC
    assert "lca.application" in LAYER_TO_SEMANTIC


def test_layer_to_semantic_values():
    assert LAYER_TO_SEMANTIC["lca.infrastructure"] == "lca.infrastructure"
    assert LAYER_TO_SEMANTIC["lca.cognition"] == "lca.cognition"
    assert LAYER_TO_SEMANTIC["lca.runtime"] == "lca.runtime"
    assert LAYER_TO_SEMANTIC["lca.agent"] == "lca.agent"
    assert LAYER_TO_SEMANTIC["lca.application"] == "lca.application"


def test_find_references_returns_all_5_keys():
    refs = find_references()
    assert set(refs.keys()) == set(LAYER_TO_SEMANTIC.keys())


def test_find_references_finds_real_imports():
    """Smoke test: find_references finds real layer imports in the repo."""
    refs = find_references()
    total = sum(len(items) for items in refs.values())
    # We know there are many references
    assert total > 100


def test_replace_imports_signature_has_dry_run():
    """Check the function signature for the dry_run parameter."""
    import inspect

    sig = inspect.signature(replace_imports)
    assert "dry_run" in sig.parameters


def test_run_git_mv_signature():
    """Check the function signature for the dry_run parameter."""
    import inspect

    sig = inspect.signature(run_git_mv)
    assert "dry_run" in sig.parameters
