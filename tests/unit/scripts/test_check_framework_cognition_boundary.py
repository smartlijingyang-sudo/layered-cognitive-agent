"""Tests for the framework/cognition boundary lint."""
from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    import sys

    path = Path(__file__).resolve().parents[3] / "scripts" / "check_framework_cognition_boundary.py"
    spec = importlib.util.spec_from_file_location("check_framework_cognition_boundary", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_framework_cognition_boundary"] = module
    spec.loader.exec_module(module)
    return module


def test_lint_clean_returns_zero() -> None:
    mod = _load_module()
    assert mod.main([]) == 0


def test_lint_whitelist_empty() -> None:
    mod = _load_module()
    assert mod.LEGACY_WHITELIST == ()


def test_lint_module_imports() -> None:
    """Sanity: the module exposes the contract the tests rely on."""
    mod = _load_module()
    assert callable(mod.main)
    assert callable(mod._violations_for)
    assert isinstance(mod.FORBIDDEN_PAIRS, tuple)
    assert isinstance(mod.LEGACY_WHITELIST, tuple)
