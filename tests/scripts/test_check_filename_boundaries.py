"""Tests for scripts/check_filename_boundaries.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from check_filename_boundaries import (  # noqa: E402
    Issue,
    all_python_files,
    check_file,
    load_legacy_blacklist,
    load_package_overrides,
    package_for_path,
)


def test_package_for_path_root():
    assert package_for_path("lca/__init__.py") == "lca"
    assert package_for_path("gateway/__init__.py") == "gateway"


def test_package_for_path_one_level():
    assert package_for_path("lca/agent/foo.py") == "lca.agent"
    assert package_for_path("lca/infrastructure/llm.py") == "lca.infrastructure"


def test_package_for_path_two_levels():
    assert package_for_path("lca/agent/orchestration_strategies/swarm.py") in ("lca.agent.orchestration_strategies", "lca.agent")


def test_package_for_path_outside_lca():
    assert package_for_path("scripts/check_foo.py") is None
    assert package_for_path("tests/test_foo.py") is None
    assert package_for_path("pyproject.toml") is None


def test_load_legacy_blacklist_empty():
    bl = load_legacy_blacklist()
    assert isinstance(bl, set)


def test_load_package_overrides_returns_dict():
    overrides = load_package_overrides()
    assert isinstance(overrides, dict)


def test_check_file_returns_none_for_normal():
    issue = check_file("lca/agent/foo.py", {})
    assert issue is None


def test_check_file_returns_issue_for_util():
    issue = check_file("lca/foo/util.py", {})
    assert issue is not None
    assert issue.kind == "new_violation"
    assert "util" in issue.message.lower()


def test_check_file_init_py_no_issue():
    issue = check_file("lca/agent/__init__.py", {})
    assert issue is None


def test_issue_render():
    issue = Issue(path="lca/foo/util.py", kind="new_violation", message="test")
    rendered = issue.render()
    assert "ERROR" in rendered
    assert "lca/foo/util.py" in rendered
    assert "test" in rendered


def test_all_python_files_excludes_vendor():
    files = all_python_files()
    paths = [str(f.relative_to(ROOT)) for f in files]
    assert not any("vendor/" in p for p in paths)
    assert not any("node_modules/" in p for p in paths)
    assert not any(".git/" in p for p in paths)
    assert not any("__pycache__" in p for p in paths)
